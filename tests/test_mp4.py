import dataclasses
import io
import struct
from collections.abc import Sequence

import pytest

from quantumfetcher import mp4
from quantumfetcher.errors import FetchError
from quantumfetcher.manifest import ClientManifest, Track
from support import (
    CHUNK,
    MANIFEST_URL,
    PPS,
    SPS,
    box,
    client_manifest,
    fragment,
    quantumstreamer_index,
)

VIDEO, _, AUDIO, _, TEXT, _ = ClientManifest.parse(MANIFEST_URL, client_manifest()).tracks
FRAGMENTS = [fragment(f"media {number}".encode() * 50) for number in range(3)]
HEADER_SIZE = len(mp4.track_header(VIDEO, 1))


def children(data: bytes) -> list[bytes]:
    return [kind for kind, _ in mp4.boxes(data)]


def find(data: bytes, *path: bytes) -> bytes:
    for kind in path:
        data = next(bytes(payload) for child, payload in mp4.boxes(data) if child == kind)
    return data


def write(track: Track, fragments: Sequence[bytes], file: io.BytesIO | None = None) -> bytes:
    file = file or io.BytesIO()
    writer = mp4.TrackWriter(file, track)
    for data in fragments[writer.fragments :]:
        writer.append(data)
    writer.finish()
    return file.getvalue()


@pytest.mark.parametrize(
    ("track", "entry", "handler"),
    [(VIDEO, b"avc1", b"vide"), (AUDIO, b"mp4a", b"soun"), (TEXT, b"stpp", b"subt")],
    ids=["video", "audio", "text"],
)
def test_header_describes_each_kind_of_track(track: Track, entry: bytes, handler: bytes) -> None:
    header = mp4.track_header(track, 7)
    assert children(header) == [b"ftyp", b"moov"]
    moov = find(header, b"moov")
    assert children(moov) == [b"mvhd", b"trak", b"mvex"]
    stbl = find(moov, b"trak", b"mdia", b"minf", b"stbl")
    assert children(stbl) == [b"stsd", b"stts", b"stsc", b"stsz", b"stco"]
    assert children(find(stbl, b"stsd")[8:]) == [entry]
    assert find(moov, b"trak", b"mdia", b"hdlr")[8:12] == handler
    assert struct.unpack(">I", find(moov, b"trak", b"tkhd")[20:24]) == (7,)
    assert struct.unpack(">I", find(moov, b"mvex", b"trex")[4:8]) == (7,)


def test_video_header_holds_the_parameter_sets() -> None:
    stbl = find(mp4.track_header(VIDEO, 1), b"moov", b"trak", b"mdia", b"minf", b"stbl")
    avc1 = find(find(stbl, b"stsd")[8:], b"avc1")
    assert struct.unpack(">HH", avc1[24:28]) == (1280, 720)
    avcc = find(avc1[78:], b"avcC")
    assert avcc[:6] == bytes([1, *SPS[1:4], 0xFF, 0xE1])
    assert avcc[6:] == struct.pack(">H", len(SPS)) + SPS + b"\1" + struct.pack(">H", len(PPS)) + PPS


def test_audio_header_holds_the_audio_configuration() -> None:
    stbl = find(mp4.track_header(AUDIO, 1), b"moov", b"trak", b"mdia", b"minf", b"stbl")
    mp4a = find(find(stbl, b"stsd")[8:], b"mp4a")
    assert struct.unpack(">HHxxxxI", mp4a[16:28]) == (6, 16, 48000 << 16)
    assert b"\x05\x02\x11\xb0" in find(mp4a[28:], b"esds")


@pytest.mark.parametrize(
    "track",
    [
        dataclasses.replace(VIDEO, fourcc="WVC1"),
        dataclasses.replace(VIDEO, codec_private_data=b""),
    ],
    ids=["other codec", "no parameter sets"],
)
def test_rejects_codecs_it_cannot_describe(track: Track) -> None:
    with pytest.raises(FetchError):
        mp4.track_header(track, 1)


def test_index_gives_the_manifest_time_and_moof_offset_of_each_fragment() -> None:
    data = write(AUDIO, FRAGMENTS)
    index = quantumstreamer_index(data)
    assert list(index) == ["0", str(CHUNK), str(2 * CHUNK)]
    for offset, expected in zip(index.values(), FRAGMENTS, strict=True):
        assert data[offset : offset + len(expected)] == expected
    assert mp4.read_fragment_index(io.BytesIO(data)) == [
        (int(time), offset) for time, offset in index.items()
    ]


def test_reads_back_the_media_data_of_each_fragment() -> None:
    data = write(TEXT, FRAGMENTS)
    assert list(mp4.read_fragments(io.BytesIO(data))) == [
        (number * CHUNK, f"media {number}".encode() * 50) for number in range(3)
    ]


@pytest.mark.parametrize(
    ("cut", "kept"),
    [(-5, 1), (0, 2), (30, 2)],
    ids=["inside the second fragment", "after the second fragment", "inside the third fragment"],
)
def test_carries_on_after_the_last_whole_fragment(cut: int, kept: int) -> None:
    whole = write(VIDEO, FRAGMENTS)
    offsets = list(quantumstreamer_index(whole).values())
    file = io.BytesIO(whole[: offsets[2] + cut])
    writer = mp4.TrackWriter(file, VIDEO)
    assert (writer.fragments, writer.size) == (kept, offsets[kept])
    assert write(VIDEO, FRAGMENTS, file) == whole


@pytest.mark.parametrize("cut", [0, 3, HEADER_SIZE, HEADER_SIZE + 50])
def test_starts_over_without_a_whole_fragment(cut: int) -> None:
    whole = write(VIDEO, FRAGMENTS)
    writer = mp4.TrackWriter(io.BytesIO(whole[:cut]), VIDEO)
    assert (writer.fragments, writer.size) == (0, 0)


def test_drops_an_index_written_before_an_interruption() -> None:
    whole = write(AUDIO, FRAGMENTS)
    assert mp4.TrackWriter(io.BytesIO(whole), AUDIO).fragments == 3
    assert write(AUDIO, FRAGMENTS, io.BytesIO(whole)) == whole


def test_finishes_only_with_every_fragment() -> None:
    with pytest.raises(FetchError, match="2 fragments but the manifest lists 3"):
        write(AUDIO, FRAGMENTS[:2])


@pytest.mark.parametrize(
    "data",
    [
        b"<html>",
        box(b"mdat", b"x"),
        box(b"moof", box(b"mfhd", bytes(8))) + box(b"mdat"),
        FRAGMENTS[0][:-1],
    ],
    ids=["not a box", "no moof", "no track", "cut off"],
)
def test_rejects_what_is_not_a_fragment(data: bytes) -> None:
    writer = mp4.TrackWriter(io.BytesIO(), AUDIO)
    with pytest.raises(FetchError):
        writer.append(data)


@pytest.mark.parametrize("data", [b"", b"short", bytes(64)], ids=["empty", "short", "zeros"])
def test_rejects_files_without_an_index(data: bytes) -> None:
    with pytest.raises(FetchError):
        mp4.read_fragment_index(io.BytesIO(data))

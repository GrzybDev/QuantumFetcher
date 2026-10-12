"""Fragmented MP4 track files as QuantumStreamer reads them: a header describing the track, the
fragments as the server sent them and an mfra box indexing when and where each fragment starts."""

import re
import struct
from collections.abc import Iterator, Sequence
from functools import reduce
from os import SEEK_END
from typing import BinaryIO

from quantumfetcher.errors import FetchError
from quantumfetcher.manifest import StreamType, Track

_BOX = struct.Struct(">I4s")
_LARGE_SIZE = struct.Struct(">Q")
_MFRO = struct.Struct(">I4sII")
_UNITY_MATRIX = struct.pack(">9I", 0x10000, 0, 0, 0, 0x10000, 0, 0, 0, 0x40000000)
_SAMPLE_ENTRY = bytes(6) + struct.pack(">H", 1)
_START_CODE = re.compile(rb"\x00\x00\x00?\x01")
_HANDLERS = {
    StreamType.VIDEO: (b"vide", b"VideoHandler"),
    StreamType.AUDIO: (b"soun", b"SoundHandler"),
    StreamType.TEXT: (b"subt", b"SubtitleHandler"),
}


def box(kind: bytes, *payload: bytes) -> bytes:
    content = b"".join(payload)
    return _BOX.pack(_BOX.size + len(content), kind) + content


def full_box(kind: bytes, version: int, flags: int, *payload: bytes) -> bytes:
    return box(kind, struct.pack(">I", version << 24 | flags), *payload)


def boxes(data: bytes | memoryview) -> Iterator[tuple[bytes, memoryview]]:
    view = memoryview(data)
    position = 0
    while position < len(view):
        if position + _BOX.size > len(view):
            raise FetchError("Truncated box header")
        size, kind = _BOX.unpack_from(view, position)
        start = position + _BOX.size
        if size == 1:
            if start + _LARGE_SIZE.size > len(view):
                raise FetchError("Truncated box header")
            (size,) = _LARGE_SIZE.unpack_from(view, start)
            start += _LARGE_SIZE.size
        elif size == 0:
            size = len(view) - position
        end = position + size
        if not start <= end <= len(view):
            raise FetchError(f"Truncated {kind.decode('latin-1')} box")
        yield kind, view[start:end]
        position = end


def fragment_track_id(fragment: bytes) -> int:
    """Check that `fragment` is a moof box followed by its mdat box and return its track ID."""
    found = list(boxes(fragment))
    if [kind for kind, _ in found] != [b"moof", b"mdat"]:
        raise FetchError("Expected a movie fragment and its media data")
    return _track_id(found[0][1])


def track_header(track: Track, track_id: int) -> bytes:
    """An ftyp and a moov box describing `track`, so that players can open its file."""
    return box(b"ftyp", b"isml", struct.pack(">I", 1), b"piff", b"iso2") + box(
        b"moov",
        full_box(
            b"mvhd",
            1,
            0,
            struct.pack(">QQIQIH10x", 0, 0, track.timescale, track.duration, 0x10000, 0x100),
            _UNITY_MATRIX,
            bytes(24),
            struct.pack(">I", track_id + 1),
        ),
        box(b"trak", _tkhd(track, track_id), _mdia(track)),
        box(
            b"mvex",
            full_box(b"mehd", 1, 0, struct.pack(">Q", track.duration)),
            full_box(b"trex", 0, 0, struct.pack(">5I", track_id, 1, 0, 0, 0)),
        ),
    )


def fragment_index(track_id: int, fragments: Sequence[tuple[int, int]]) -> bytes:
    tfra = full_box(
        b"tfra",
        1,
        0,
        struct.pack(">III", track_id, 0, len(fragments)),
        *(struct.pack(">QQBBB", time, offset, 1, 1, 1) for time, offset in fragments),
    )
    mfra_size = _BOX.size + len(tfra) + _MFRO.size
    return box(b"mfra", tfra, full_box(b"mfro", 0, 0, struct.pack(">I", mfra_size)))


def read_fragment_index(file: BinaryIO) -> list[tuple[int, int]]:
    end = file.seek(0, SEEK_END)
    file.seek(max(end - _MFRO.size, 0))
    try:
        mfro_size, kind, _, mfra_size = _MFRO.unpack(file.read(_MFRO.size))
    except struct.error:
        mfro_size, kind, mfra_size = 0, b"", 0
    if (mfro_size, kind) != (_MFRO.size, b"mfro") or mfra_size > end:
        raise FetchError("No fragment index at the end of the file")
    file.seek(end - mfra_size)
    tfra = _find(file.read(mfra_size), b"mfra", b"tfra")
    try:
        version = tfra[0]
        _, sizes, count = struct.unpack_from(">III", tfra, 4)
        entry = struct.Struct(">QQ" if version == 1 else ">II")
        # Each entry ends with traf, trun and sample numbers of the sizes the flags give.
        stride = entry.size + sum((sizes >> shift & 3) + 1 for shift in (4, 2, 0))
        return [entry.unpack_from(tfra, 16 + index * stride) for index in range(count)]
    except (IndexError, struct.error) as error:
        raise FetchError("Truncated fragment index") from error


def read_fragments(file: BinaryIO) -> Iterator[tuple[int, bytes]]:
    for time, offset in read_fragment_index(file):
        file.seek(offset)
        moof_size = _expect_box(file, b"moof")
        file.seek(offset + moof_size)
        mdat_size = _expect_box(file, b"mdat")
        yield time, file.read(mdat_size - _BOX.size)


class TrackWriter:
    """Writes a track file one fragment at a time, keeping what an interrupted write left in it."""

    def __init__(self, file: BinaryIO, track: Track) -> None:
        self._file = file
        self._track = track
        self._offsets: list[int] = []
        self._track_id = 0
        self.size = self._resume()

    @property
    def fragments(self) -> int:
        return len(self._offsets)

    def append(self, fragment: bytes) -> None:
        track_id = fragment_track_id(fragment)
        if not self._offsets:
            self._track_id = track_id
            self._write(track_header(self._track, track_id))
        self._offsets.append(self.size)
        self._write(fragment)

    def finish(self) -> None:
        if len(self._offsets) != len(self._track.start_times):
            raise FetchError(
                f"The file has {len(self._offsets)} fragments "
                f"but the manifest lists {len(self._track.start_times)}"
            )
        self._write(
            fragment_index(
                self._track_id, list(zip(self._track.start_times, self._offsets, strict=True))
            )
        )

    def _write(self, data: bytes) -> None:
        self._file.seek(self.size)
        self._file.write(data)
        self.size += len(data)

    def _resume(self) -> int:
        """Keep the header and the whole fragments in the file, returning the size they take."""
        layout = list(_complete_boxes(self._file))
        size = 0
        if [kind for kind, _, _ in layout[:2]] == [b"ftyp", b"moov"]:
            for (moof, offset, _), (mdat, start, length) in zip(
                layout[2::2], layout[3::2], strict=False
            ):
                if (moof, mdat) != (b"moof", b"mdat"):
                    break
                self._offsets.append(offset)
                size = start + length
        if self._offsets:
            self._file.seek(self._offsets[0])
            moof_size = _expect_box(self._file, b"moof")
            self._file.seek(self._offsets[0])
            self._track_id = _track_id(_find(self._file.read(moof_size), b"moof"))
        self._file.truncate(size)
        return size


def _tkhd(track: Track, track_id: int) -> bytes:
    volume = 0x100 if track.type is StreamType.AUDIO else 0
    return full_box(
        b"tkhd",
        1,
        0x7,  # Enabled, in the movie and in its preview.
        struct.pack(">QQI4xQ8xHHH2x", 0, 0, track_id, track.duration, 0, 0, volume),
        _UNITY_MATRIX,
        struct.pack(">II", (track.width or 0) << 16, (track.height or 0) << 16),
    )


def _mdia(track: Track) -> bytes:
    handler, name = _HANDLERS[track.type]
    media_header = {
        StreamType.VIDEO: full_box(b"vmhd", 0, 1, bytes(8)),
        StreamType.AUDIO: full_box(b"smhd", 0, 0, bytes(4)),
        StreamType.TEXT: full_box(b"sthd", 0, 0),
    }[track.type]
    language = _language(track.language)
    return box(
        b"mdia",
        full_box(
            b"mdhd",
            1,
            0,
            struct.pack(">QQIQHH", 0, 0, track.timescale, track.duration, language, 0),
        ),
        full_box(b"hdlr", 0, 0, bytes(4), handler, bytes(12), name, b"\0"),
        box(
            b"minf",
            media_header,
            box(b"dinf", full_box(b"dref", 0, 0, struct.pack(">I", 1), full_box(b"url ", 0, 1))),
            box(
                b"stbl",
                full_box(b"stsd", 0, 0, struct.pack(">I", 1), _sample_entry(track)),
                full_box(b"stts", 0, 0, bytes(4)),
                full_box(b"stsc", 0, 0, bytes(4)),
                full_box(b"stsz", 0, 0, bytes(8)),
                full_box(b"stco", 0, 0, bytes(4)),
            ),
        ),
    )


def _sample_entry(track: Track) -> bytes:
    match track.type, track.fourcc:
        case StreamType.VIDEO, "H264" | "AVC1":
            size = struct.pack(">HH", track.width or 0, track.height or 0)
            resolution = struct.pack(">IIIH32sHh", 0x480000, 0x480000, 0, 1, b"", 0x18, -1)
            return box(b"avc1", _SAMPLE_ENTRY, bytes(16), size, resolution, _avcc(track))
        case StreamType.AUDIO, "AACL":
            audio = struct.pack(
                ">8xHH4xI",
                track.channels or 2,
                track.bits_per_sample or 16,
                (track.sampling_rate or 0) << 16,
            )
            return box(b"mp4a", _SAMPLE_ENTRY, audio, _esds(track))
        case StreamType.TEXT, "TTML":
            return box(b"stpp", _SAMPLE_ENTRY, b"http://www.w3.org/ns/ttml\0", b"\0", b"\0")
    raise FetchError(f"Cannot describe {track.type} tracks in {track.fourcc or 'unknown codecs'}")


def _avcc(track: Track) -> bytes:
    units = [unit for unit in _START_CODE.split(track.codec_private_data) if unit]
    sps = [unit for unit in units if unit[0] & 0x1F == 7]
    pps = [unit for unit in units if unit[0] & 0x1F == 8]
    if not sps or not pps:
        raise FetchError("The video codec data lacks a sequence or picture parameter set")
    return box(
        b"avcC",
        bytes([1, *sps[0][1:4], 0xFC | track.nal_unit_length - 1, 0xE0 | len(sps)]),
        *(struct.pack(">H", len(unit)) + unit for unit in sps),
        bytes([len(pps)]),
        *(struct.pack(">H", len(unit)) + unit for unit in pps),
    )


def _esds(track: Track) -> bytes:
    # Audio stream (5) of ISO/IEC 14496-3 audio (0x40), with the codec data as its configuration.
    decoder = struct.pack(">BB3xII", 0x40, 5 << 2 | 1, track.bitrate, track.bitrate)
    return full_box(
        b"esds",
        0,
        0,
        _descriptor(
            0x03,
            struct.pack(">HB", 0, 0),
            _descriptor(0x04, decoder, _descriptor(0x05, track.codec_private_data)),
            _descriptor(0x06, b"\x02"),
        ),
    )


def _descriptor(tag: int, *payload: bytes) -> bytes:
    content = b"".join(payload)
    size = len(content)
    length = [size & 0x7F]
    while size := size >> 7:
        length.insert(0, size & 0x7F | 0x80)
    return bytes([tag, *length]) + content


def _language(code: str | None) -> int:
    """An ISO 639-2 code as three 5-bit letters, the way mdhd stores it."""
    if not (code and len(code) == 3 and code.isascii() and code.isalpha() and code.islower()):
        code = "und"
    return reduce(lambda packed, letter: packed << 5 | ord(letter) - 0x60, code, 0)


def _track_id(moof: memoryview) -> int:
    return struct.unpack_from(">I", _find(moof, b"traf", b"tfhd"), 4)[0]


def _find(data: bytes | memoryview, *path: bytes) -> memoryview:
    found = memoryview(data)
    for kind in path:
        found = next((payload for child, payload in boxes(found) if child == kind), None)
        if found is None:
            raise FetchError(f"No {kind.decode('latin-1')} box")
    return found


def _complete_boxes(file: BinaryIO) -> Iterator[tuple[bytes, int, int]]:
    """Yield the type, offset and size of each top-level box until one is cut off."""
    end = file.seek(0, SEEK_END)
    offset = 0
    while offset < end:
        file.seek(offset)
        header = file.read(_BOX.size)
        if len(header) < _BOX.size:
            return
        size, kind = _BOX.unpack(header)
        if size == 1:
            large = file.read(_LARGE_SIZE.size)
            if len(large) < _LARGE_SIZE.size:
                return
            (size,) = _LARGE_SIZE.unpack(large)
        if size < _BOX.size or offset + size > end:
            return
        yield kind, offset, size
        offset += size


def _expect_box(file: BinaryIO, kind: bytes) -> int:
    header = file.read(_BOX.size)
    if len(header) < _BOX.size or _BOX.unpack(header)[1] != kind:
        raise FetchError(f"Expected a {kind.decode('latin-1')} box")
    return _BOX.unpack(header)[0]

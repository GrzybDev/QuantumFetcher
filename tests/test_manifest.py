import xml.etree.ElementTree as ET

import pytest

from quantumfetcher.errors import FetchError
from quantumfetcher.manifest import ClientManifest, StreamType
from support import (
    CHUNK,
    MANIFEST_URL,
    PPS,
    SPS,
    client_manifest,
    episode_manifest,
    fragment_url,
    track,
)


def test_reads_a_track_for_each_quality_level() -> None:
    assert [
        (track.type, track.name, track.language, track.bitrate)
        for track in episode_manifest().tracks
    ] == [
        (StreamType.VIDEO, "video", None, 2_000_000),
        (StreamType.VIDEO, "video", None, 500_000),
        (StreamType.AUDIO, "enus", "eng", 256000),
        (StreamType.AUDIO, "esmx", "spa", 256000),
        (StreamType.TEXT, "enus_captions", "eng", 256000),
        (StreamType.TEXT, "eses_captions", "spa", 256000),
    ]


def test_reads_what_describing_a_track_needs() -> None:
    video, audio = track("video", 500_000), track("enus")
    assert (video.fourcc, video.width, video.height) == ("H264", 640, 360)
    assert video.codec_private_data == b"\0\0\0\1" + SPS + b"\0\0\0\1" + PPS
    assert (audio.fourcc, audio.sampling_rate, audio.channels, audio.bits_per_sample) == (
        "AACL",
        48000,
        6,
        16,
    )
    assert audio.codec_private_data == b"\x11\xb0"
    assert (audio.timescale, audio.duration) == (10_000_000, 3 * CHUNK)


def test_fragments_sit_next_to_the_manifest_and_keep_its_query() -> None:
    captions = track("enus_captions")
    assert captions.start_times == (0, CHUNK, 2 * CHUNK)
    assert captions.fragment_url(CHUNK) == fragment_url("enus_captions", 256000, CHUNK)


def test_timeline_follows_durations_times_and_repeats() -> None:
    xml = (
        b'<SmoothStreamingMedia Duration="155"><StreamIndex Type="audio" Name="a" '
        b'Url="Q({bitrate})/F(a={start_time})"><QualityLevel Bitrate="1" FourCC="AACL"/>'
        b'<c t="100" d="10"/><c d="20" r="2"/><c d="5"/></StreamIndex></SmoothStreamingMedia>'
    )
    (audio,) = ClientManifest.parse("http://cdn.test/a.ism/Manifest", xml).tracks
    assert (audio.start_times, audio.duration) == ((100, 110, 130, 150), 155)
    assert audio.fragment_url(130) == "http://cdn.test/a.ism/Q(1)/F(a=130)"


def test_skips_streams_of_unknown_types() -> None:
    xml = b'<SmoothStreamingMedia><StreamIndex Type="data" Url="x"/></SmoothStreamingMedia>'
    assert ClientManifest.parse("http://cdn.test/m", xml).tracks == ()


@pytest.mark.parametrize(
    "xml",
    [
        b"not xml",
        b"<html/>",
        client_manifest().replace(b'Bitrate="500000"', b'Bitrate="fast"'),
    ],
    ids=["not xml", "another document", "invalid bitrate"],
)
def test_rejects_invalid_manifests(xml: bytes) -> None:
    with pytest.raises(FetchError):
        ClientManifest.parse(MANIFEST_URL, xml)


def test_local_copy_offers_only_the_kept_tracks() -> None:
    kept = [track("video", 500_000), track("esmx"), track("enus_captions")]
    streams = ET.fromstring(episode_manifest().local_copy(kept)).findall("StreamIndex")
    assert [
        (stream.get("Type"), stream.get("Name"), stream.get("QualityLevels")) for stream in streams
    ] == [("video", None, "1"), ("audio", "esmx", "1"), ("text", "enus_captions", "1")]
    video = streams[0]
    (level,) = video.findall("QualityLevel")
    assert (level.get("Index"), level.get("Bitrate")) == ("0", "500000")
    assert (video.get("MaxWidth"), video.get("MaxHeight")) == ("640", "360")
    assert [chunk.attrib for chunk in video.findall("c")] == [
        {"n": str(number), "d": str(CHUNK)} for number in range(3)
    ]

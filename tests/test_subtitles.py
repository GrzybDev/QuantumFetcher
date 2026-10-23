import io
from pathlib import Path

import pytest

from quantumfetcher import subtitles
from quantumfetcher.errors import FetchError
from quantumfetcher.manifest import ClientManifest
from quantumfetcher.mp4 import TrackWriter
from quantumfetcher.subtitles import Cue
from support import CHUNK, MANIFEST_URL, caption, client_manifest, fragment, ttml


def test_reads_captions_with_their_line_breaks() -> None:
    document = ttml(
        '<p begin="00:00:01.250" end="00:00:02.5">\n  <span style="textStyle">'
        "- Line one,<br/>\r\n   - <span>line</span> two  </span></p>"
    )
    assert list(subtitles.parse_ttml(document, 10)) == [Cue(11.25, 12.5, "- Line one,\n- line two")]


def test_reads_offset_times() -> None:
    document = ttml(caption("1.5s", "1500ms", "a"), caption("0.5m", "1h", "b"))
    assert [(cue.start, cue.end) for cue in subtitles.parse_ttml(document, 0)] == [
        (1.5, 1.5),
        (30, 3600),
    ]


@pytest.mark.parametrize(
    "document",
    [ttml(caption("10f", "20f", "a")), ttml('<p begin="1s">a</p>'), b"<tt"],
    ids=["frames", "no end", "not xml"],
)
def test_rejects_captions_it_cannot_time(document: bytes) -> None:
    with pytest.raises(FetchError):
        list(subtitles.parse_ttml(document, 0))


def test_srt_orders_the_cues_and_joins_the_pieces_of_split_ones() -> None:
    cues = [
        Cue(4, 6, "Second"),
        Cue(1, 2, "First"),
        Cue(6.05, 7, "Second"),
        Cue(8, 9, "  "),
        Cue(9, 10, "Second"),
    ]
    assert subtitles.to_srt(cues) == (
        "1\n00:00:01,000 --> 00:00:02,000\nFirst\n\n"
        "2\n00:00:04,000 --> 00:00:07,000\nSecond\n\n"
        "3\n00:00:09,000 --> 00:00:10,000\nSecond\n"
    )


def test_srt_times_round_to_milliseconds() -> None:
    srt = subtitles.to_srt([Cue(3599.9994, 3599.9996, "a")])
    assert "00:59:59,999 --> 01:00:00,000" in srt


@pytest.mark.parametrize(
    ("episode", "title"),
    [
        ("J1A", "EPISODE 1: Monarch Solutions"),
        ("J4BB-X1-X2", "EPISODE 4: The Lifeboat Protocol"),
        ("J1 - 4K Test", "EPISODE 1: Monarch Solutions"),
        ("J9A", None),
        ("X1", None),
    ],
)
def test_episode_title_follows_the_episode_number(episode: str, title: str | None) -> None:
    cue = subtitles.episode_title(episode)
    assert (cue and cue.text) == title
    assert subtitles.episode_title("J2A") == Cue(7.5, 9.833, "EPISODE 2: Prisoner")


def test_reads_the_cues_of_a_downloaded_text_track(tmp_path: Path) -> None:
    manifest = ClientManifest.parse(MANIFEST_URL, client_manifest(chunks=2))
    track = next(track for track in manifest.tracks if track.name == "enus_captions")
    path = tmp_path / "track.ismt"
    file = io.BytesIO()
    writer = TrackWriter(file, track)
    for number in range(2):
        writer.append(fragment(ttml(caption("00:00:00.5", "00:00:01", f"line {number}"))))
    writer.finish()
    path.write_bytes(file.getvalue())
    assert subtitles.read_cues(path, track.timescale) == [
        Cue(0.5, 1, "line 0"),
        Cue(CHUNK / 10**7 + 0.5, CHUNK / 10**7 + 1, "line 1"),
    ]

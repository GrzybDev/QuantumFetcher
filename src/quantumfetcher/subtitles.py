"""SubRip subtitles from the TTML captions of a text track, which QuantumStreamer shows instead of
the track's own captions when they are saved as <track name>.srt in the episode folder."""

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, replace
from pathlib import Path

from quantumfetcher.errors import FetchError
from quantumfetcher.mp4 import read_fragments

EPISODE_TITLES = {
    1: "Monarch Solutions",
    2: "Prisoner",
    3: "Deception",
    4: "The Lifeboat Protocol",
}

_TTML = "{http://www.w3.org/ns/ttml}"
_CLOCK_TIME = re.compile(r"(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")
_OFFSET_TIME = re.compile(r"(\d+(?:\.\d+)?)(h|m|s|ms)")
_OFFSET_UNITS = {"h": 3600, "m": 60, "s": 1, "ms": 0.001}
_EPISODE_NUMBER = re.compile(r"J(\d+)")
# When the title card is on screen in every episode.
_TITLE_START, _TITLE_END = 7.5, 9.833
# A caption spanning fragments comes in pieces this close together.
_SPLIT_GAP = 0.1


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str


def read_cues(path: Path, timescale: int) -> list[Cue]:
    """The captions of every fragment of a downloaded text track, timed from the episode start."""
    with path.open("rb") as file:
        return [
            cue
            for start_time, document in read_fragments(file)
            for cue in parse_ttml(document, start_time / timescale)
        ]


def parse_ttml(document: bytes, offset: float) -> Iterator[Cue]:
    """The paragraphs of a TTML document, with times relative to `offset` seconds."""
    try:
        root = ET.fromstring(document)
    except ET.ParseError as error:
        raise FetchError(f"Invalid captions: {error}") from error
    for paragraph in root.iter(f"{_TTML}p"):
        begin, end = paragraph.get("begin"), paragraph.get("end")
        if begin is None or end is None:
            raise FetchError("A caption without its begin and end time")
        yield Cue(offset + _seconds(begin), offset + _seconds(end), _text(paragraph))


def episode_title(episode_id: str) -> Cue | None:
    """A cue with the title of the episode `episode_id` belongs to, such as J1A to episode 1."""
    match = _EPISODE_NUMBER.match(episode_id)
    title = EPISODE_TITLES.get(int(match[1])) if match else None
    return Cue(_TITLE_START, _TITLE_END, f"EPISODE {match[1]}: {title}") if title else None


def to_srt(cues: Iterable[Cue]) -> str:
    """SubRip subtitles of the non-empty cues in time order, joining the pieces of split ones."""
    merged: list[Cue] = []
    for cue in sorted(cues, key=lambda cue: cue.start):
        if not cue.text.strip():
            continue
        if merged and merged[-1].text == cue.text and cue.start - merged[-1].end < _SPLIT_GAP:
            merged[-1] = replace(merged[-1], end=max(merged[-1].end, cue.end))
        else:
            merged.append(cue)
    return "\n".join(
        f"{number}\n{_timestamp(cue.start)} --> {_timestamp(cue.end)}\n{cue.text}\n"
        for number, cue in enumerate(merged, 1)
    )


def _seconds(time: str) -> float:
    if match := _CLOCK_TIME.fullmatch(time):
        hours, minutes, seconds = match.groups()
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    if match := _OFFSET_TIME.fullmatch(time):
        return float(match[1]) * _OFFSET_UNITS[match[2]]
    raise FetchError(f"Unsupported caption time {time!r}")


def _text(paragraph: ET.Element) -> str:
    """The text of a paragraph, with its line breaks but not the source's own formatting."""

    def flatten(element: ET.Element) -> Iterator[str]:
        yield _unwrap(element.text)
        for child in element:
            yield "\n" if child.tag == f"{_TTML}br" else "".join(flatten(child))
            yield _unwrap(child.tail)

    return "\n".join(line.strip() for line in "".join(flatten(paragraph)).split("\n"))


def _unwrap(text: str | None) -> str:
    return (text or "").replace("\r", "").replace("\n", "")


def _timestamp(seconds: float) -> str:
    hours, milliseconds = divmod(round(seconds * 1000), 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

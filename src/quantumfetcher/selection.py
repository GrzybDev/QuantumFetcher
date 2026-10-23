"""Which tracks of each episode to download, picked by selectors such as best, 1080p or enus.

A selector picks the tracks it names by stream name (enus_captions), locale (enus), ISO 639-2
language (eng), height (1080p) or bitrate (12000000); all picks every track, best the one with the
highest bitrate and none nothing.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from operator import attrgetter

from quantumfetcher.manifest import StreamType, Track

ALL = "all"
BEST = "best"
NONE = "none"
DEFAULTS: Mapping[StreamType, tuple[str, ...]] = {
    StreamType.VIDEO: (BEST,),
    StreamType.AUDIO: ("enus",),
    StreamType.TEXT: ("enus",),
}

_LANGUAGES = {
    "deu": "German",
    "eng": "English",
    "fra": "French",
    "ita": "Italian",
    "jpn": "Japanese",
    "kor": "Korean",
    "por": "Portuguese",
    "rus": "Russian",
    "spa": "Spanish",
    "zho": "Chinese",
}


@dataclass(frozen=True)
class Option:
    """A selector offered for the tracks of one type, with what it picks across the episodes.

    Attributes:
        type: The type of the tracks it picks.
        selector: The selector, as the command line takes it.
        description: What the tracks hold, such as their resolution, codec and bitrate.
        size: The average estimated size of a track it picks, or None when none has an estimate.
        episodes: The number of episodes it picks a track in.
    """

    type: StreamType
    selector: str
    description: str
    size: int | None
    episodes: int


def select(tracks: Iterable[Track], selectors: Iterable[str]) -> list[Track]:
    """The tracks the selectors pick, in the order of `tracks`.

    Args:
        tracks: The tracks to pick from.
        selectors: The selectors, in any letter case.
    """
    tracks = list(tracks)
    selectors = {selector.casefold() for selector in selectors}
    best = max(tracks, key=attrgetter("bitrate"), default=None) if BEST in selectors else None
    return [
        track
        for track in tracks
        if track is best or any(selector in _names(track) for selector in selectors)
    ]


def unknown(selectors: Iterable[str], tracks: Iterable[Track]) -> list[str]:
    """The selectors that pick none of `tracks`, other than best and none.

    Args:
        selectors: The selectors to check.
        tracks: The tracks they pick from.
    """
    names = set().union(*map(_names, tracks))
    return [
        selector
        for selector in selectors
        if selector.casefold() not in {BEST, NONE} and selector.casefold() not in names
    ]


def options(episodes: Iterable[Sequence[Track]]) -> list[Option]:
    """What to choose from the tracks of the episodes: one option for each selector of a track.

    Best comes first when there is video, then video by falling bitrate, then audio and text in
    the order the episodes list them.

    Args:
        episodes: The tracks of each episode.
    """
    episodes = list(episodes)
    groups: dict[tuple[StreamType, str], list[Track]] = {}
    for track in sorted((track for tracks in episodes for track in tracks), key=_order):
        groups.setdefault((track.type, selector(track)), []).append(track)
    found = [
        Option(
            type=stream_type,
            selector=name,
            description=_describe(group[0]),
            size=_average_size(group),
            episodes=len(group),
        )
        for (stream_type, name), group in groups.items()
    ]
    best = [
        track for tracks in episodes for track in select(of_type(tracks, StreamType.VIDEO), [BEST])
    ]
    if best:
        description = "The highest bitrate of each episode"
        found.insert(0, Option(StreamType.VIDEO, BEST, description, _average_size(best), len(best)))
    return found


def defaults(kind: StreamType, episodes: Iterable[Sequence[Track]]) -> set[str]:
    """The options the default selectors of `kind` pick in any of the episodes.

    Args:
        kind: The type of the tracks.
        episodes: The tracks of each episode.
    """
    named = [default for default in DEFAULTS[kind] if default != BEST]
    picked = {
        selector(track) for tracks in episodes for track in select(of_type(tracks, kind), named)
    }
    return picked | ({BEST} & set(DEFAULTS[kind]))


def of_type(tracks: Iterable[Track], kind: StreamType) -> list[Track]:
    """Keep the tracks of one type, in their order.

    Args:
        tracks: The tracks to keep from.
        kind: The type to keep.
    """
    return [track for track in tracks if track.type is kind]


def selector(track: Track) -> str:
    """The selector that picks this track and no other track of its episode.

    Args:
        track: The track to pick.
    """
    return str(track.bitrate) if track.type is StreamType.VIDEO else track.name


def _names(track: Track) -> set[str]:
    """The casefolded selectors that pick `track` by name, such as all, enus, eng or 1080p.

    Args:
        track: The track to name.
    """
    names = {ALL, track.name, track.locale, str(track.bitrate)}
    if track.language:
        names.add(track.language)
    if track.height:
        names.add(f"{track.height}p")
    return {name.casefold() for name in names}


def _order(track: Track) -> tuple[int, int]:
    """Sort key listing video by falling bitrate, then audio and text in their own order.

    Args:
        track: The track to place.
    """
    position = list(StreamType).index(track.type)
    return position, -track.bitrate if track.type is StreamType.VIDEO else 0


def _describe(track: Track) -> str:
    language = _LANGUAGES.get(track.language or "", track.language or "unknown language")
    match track.type:
        case StreamType.VIDEO:
            return (
                f"{track.height}p, {track.width}x{track.height} {track.fourcc}, "
                f"{track.bitrate / 1_000_000:.1f} Mbps"
            )
        case StreamType.AUDIO:
            return (
                f"{language}, {track.fourcc} {track.channels} ch "
                f"{(track.sampling_rate or 0) / 1000:g} kHz, {track.bitrate // 1000} kbps"
            )
        case StreamType.TEXT:
            return f"{language}, {track.fourcc}"


def _average_size(tracks: list[Track]) -> int | None:
    sizes = [size for track in tracks if (size := track.estimated_size) is not None]
    return sum(sizes) // len(sizes) if sizes else None

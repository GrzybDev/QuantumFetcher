import dataclasses
from collections.abc import Iterable

import pytest

from quantumfetcher import selection
from quantumfetcher.manifest import StreamType, Track
from support import episode_manifest

TRACKS = episode_manifest().tracks


def keys(tracks: Iterable[Track]) -> list[tuple[str, int]]:
    return [(track.name, track.bitrate) for track in tracks]


@pytest.mark.parametrize(
    ("kind", "selectors", "expected"),
    [
        (StreamType.VIDEO, ["best"], [("video", 2_000_000)]),
        (StreamType.VIDEO, ["360p"], [("video", 500_000)]),
        (StreamType.VIDEO, ["500000", "best"], [("video", 2_000_000), ("video", 500_000)]),
        (StreamType.VIDEO, ["all"], [("video", 2_000_000), ("video", 500_000)]),
        (StreamType.VIDEO, ["none"], []),
        (StreamType.VIDEO, [], []),
        (StreamType.AUDIO, ["esmx"], [("esmx", 256000)]),
        (StreamType.AUDIO, ["ENG"], [("enus", 256000)]),
        (StreamType.AUDIO, ["spa", "enus"], [("enus", 256000), ("esmx", 256000)]),
        (StreamType.TEXT, ["enus"], [("enus_captions", 256000)]),
        (StreamType.TEXT, ["eses_captions"], [("eses_captions", 256000)]),
    ],
)
def test_selectors_pick_tracks_by_what_names_them(
    kind: StreamType, selectors: list[str], expected: list[tuple[str, int]]
) -> None:
    assert keys(selection.select(selection.of_type(TRACKS, kind), selectors)) == expected


def test_unknown_lists_the_selectors_that_pick_nothing() -> None:
    audio = selection.of_type(TRACKS, StreamType.AUDIO)
    assert selection.unknown(["enus", "best", "None", "pl", "720p"], audio) == ["pl", "720p"]


def test_offers_best_then_each_track_once_with_its_average_size() -> None:
    shorter = [dataclasses.replace(track, duration=track.duration // 3) for track in TRACKS]
    options = selection.options([TRACKS, shorter[:3]])
    assert [(option.type, option.selector, option.episodes) for option in options] == [
        (StreamType.VIDEO, "best", 2),
        (StreamType.VIDEO, "2000000", 2),
        (StreamType.VIDEO, "500000", 2),
        (StreamType.AUDIO, "enus", 2),
        (StreamType.AUDIO, "esmx", 1),
        (StreamType.TEXT, "enus_captions", 1),
        (StreamType.TEXT, "eses_captions", 1),
    ]
    full = 2_000_000 * 6 // 8
    assert [options[0].size, options[1].size] == [(full + full // 3) // 2] * 2
    assert options[5].size is None
    assert options[2].description == "360p, 640x360 H264, 0.5 Mbps"
    assert options[4].description == "Spanish, AACL 6 ch 48 kHz, 256 kbps"
    assert options[5].description == "English, TTML"


def test_defaults_name_the_options_picked_in_each_episode() -> None:
    lower = [track for track in TRACKS if track.bitrate != 2_000_000]
    episodes = [TRACKS, lower]
    assert selection.defaults(StreamType.VIDEO, episodes) == {"best"}
    assert selection.defaults(StreamType.AUDIO, episodes) == {"enus"}
    assert selection.defaults(StreamType.TEXT, episodes) == {"enus_captions"}
    best = [
        keys(selection.select(selection.of_type(tracks, StreamType.VIDEO), ["best"]))
        for tracks in episodes
    ]
    assert best == [[("video", 2_000_000)], [("video", 500_000)]]

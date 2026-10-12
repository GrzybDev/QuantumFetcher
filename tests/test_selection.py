import dataclasses
import unittest

from quantumfetcher import selection
from quantumfetcher.manifest import ClientManifest, StreamType
from support import MANIFEST_URL, client_manifest


def keys(tracks):
    return [(track.name, track.bitrate) for track in tracks]


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.tracks = ClientManifest.parse(MANIFEST_URL, client_manifest()).tracks

    def of_type(self, kind):
        return [track for track in self.tracks if track.type is kind]

    def test_selectors_pick_tracks_by_what_names_them(self):
        video, audio = self.of_type(StreamType.VIDEO), self.of_type(StreamType.AUDIO)
        cases = [
            (video, ["best"], [("video", 2_000_000)]),
            (video, ["360p"], [("video", 500_000)]),
            (video, ["500000", "best"], [("video", 2_000_000), ("video", 500_000)]),
            (video, ["all"], [("video", 2_000_000), ("video", 500_000)]),
            (video, ["none"], []),
            (video, [], []),
            (audio, ["esmx"], [("esmx", 256000)]),
            (audio, ["ENG"], [("enus", 256000)]),
            (audio, ["spa", "enus"], [("enus", 256000), ("esmx", 256000)]),
            (self.of_type(StreamType.TEXT), ["enus"], [("enus_captions", 256000)]),
            (self.of_type(StreamType.TEXT), ["eses_captions"], [("eses_captions", 256000)]),
        ]
        for tracks, selectors, expected in cases:
            with self.subTest(selectors=selectors):
                self.assertEqual(keys(selection.select(tracks, selectors)), expected)

    def test_unknown_lists_the_selectors_that_pick_nothing(self):
        audio = self.of_type(StreamType.AUDIO)
        self.assertEqual(
            selection.unknown(["enus", "best", "None", "pl", "720p"], audio), ["pl", "720p"]
        )

    def test_offers_best_then_each_track_once_with_its_average_size(self):
        shorter = [
            dataclasses.replace(track, duration=track.duration // 3) for track in self.tracks
        ]
        options = selection.options([self.tracks, shorter[:3]])
        self.assertEqual(
            [(option.type, option.selector, option.episodes) for option in options],
            [
                (StreamType.VIDEO, "best", 2),
                (StreamType.VIDEO, "2000000", 2),
                (StreamType.VIDEO, "500000", 2),
                (StreamType.AUDIO, "enus", 2),
                (StreamType.AUDIO, "esmx", 1),
                (StreamType.TEXT, "enus_captions", 1),
                (StreamType.TEXT, "eses_captions", 1),
            ],
        )
        full = 2_000_000 * 6 // 8
        self.assertEqual([options[0].size, options[1].size], [(full + full // 3) // 2] * 2)
        self.assertIsNone(options[5].size)
        self.assertEqual(options[2].description, "360p, 640x360 H264, 0.5 Mbps")
        self.assertEqual(options[4].description, "Spanish, AACL 6 ch 48 kHz, 256 kbps")
        self.assertEqual(options[5].description, "English, TTML")

    def test_defaults_name_the_options_picked_in_each_episode(self):
        lower = [track for track in self.tracks if track.bitrate != 2_000_000]
        episodes = [self.tracks, lower]
        self.assertEqual(selection.defaults(StreamType.VIDEO, episodes), {"best"})
        self.assertEqual(selection.defaults(StreamType.AUDIO, episodes), {"enus"})
        self.assertEqual(selection.defaults(StreamType.TEXT, episodes), {"enus_captions"})
        videos = [
            keys(selection.select([t for t in tracks if t.type is StreamType.VIDEO], ["best"]))
            for tracks in episodes
        ]
        self.assertEqual(videos, [[("video", 2_000_000)], [("video", 500_000)]])


if __name__ == "__main__":
    unittest.main()

import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from rich.progress import Progress

from quantumfetcher import selection
from quantumfetcher.download import TrackDownloader
from quantumfetcher.episodes import Episode, EpisodeDownloader, fetch_episodes
from quantumfetcher.manifest import ClientManifest
from support import MANIFEST_URL, FakeClient, episode_responses
from test_mp4 import quantumstreamer_index

SMIL = "{http://www.w3.org/2001/SMIL20/Language}"


def files(folder: Path) -> list[str]:
    return sorted(path.name for path in folder.iterdir())


def served_locally(folder: Path) -> tuple[int, int]:
    """Replay QuantumStreamer: count the fragment requests the local client manifest leads to
    that it would serve from the episode's files, and those it would fetch from the server."""
    (ism,) = folder.glob("*.ism")
    root = ET.parse(ism).getroot()
    meta = root.find(f"{SMIL}head/{SMIL}meta[@name='clientManifestRelativePath']")
    media = {}
    for tag in ("video", "audio", "textstream"):
        for element in root.iter(f"{SMIL}{tag}"):
            name = "video"
            if tag != "video":
                name = element.find(f"{SMIL}param[@name='trackName']").get("value")
            index = quantumstreamer_index((folder / element.get("src")).read_bytes())
            media[f"{name}_{element.get('systemBitrate')}"] = index
    served = fetched = 0
    for stream in ET.parse(folder / meta.get("content")).getroot().findall("StreamIndex"):
        name = re.search(r"Fragments\((\w+)=", stream.get("Url"))[1]
        times, time = [], 0
        for chunk in stream.findall("c"):
            times.append(time)
            time += int(chunk.get("d"))
        for level in stream.findall("QualityLevel"):
            index = media.get(f"{name}_{level.get('Bitrate')}", {})
            served += sum(str(time) in index for time in times)
            fetched += sum(str(time) not in index for time in times)
    return served, fetched


class EpisodeDownloaderTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.client = FakeClient(episode_responses())
        self.episode = Episode(
            "J1A", ClientManifest.parse(MANIFEST_URL, self.client.get(MANIFEST_URL))
        )
        self.folder = self.root / "J1A"

    def tracks(self, *selectors):
        return selection.select(self.episode.manifest.tracks, selectors)

    def download(self, tracks, **options):
        downloader = TrackDownloader(self.client, 2)
        episodes = EpisodeDownloader(downloader, self.root, Progress(disable=True), **options)
        return episodes.download_all([(self.episode, tracks)])

    def test_saves_tracks_with_manifests_quantumstreamer_plays_offline(self):
        self.assertEqual(self.download(self.tracks("500000", "esmx", "enus_captions")), [])
        self.assertEqual(
            files(self.folder),
            [
                "J1A.ism",
                "J1A.ismc",
                "J1A_enus_captions_256000.ismt",
                "J1A_esmx_256000.isma",
                "J1A_video_500000.ismv",
            ],
        )
        self.assertEqual(served_locally(self.folder), (9, 0))

    def test_manifests_offer_the_tracks_of_earlier_downloads(self):
        self.download(self.tracks("enus_captions"))
        self.download(self.tracks("500000", "esmx"))
        self.assertEqual(served_locally(self.folder), (9, 0))

    def test_moves_aside_server_manifests_quantumstreamer_could_use_instead(self):
        self.folder.mkdir()
        (self.folder / "QUANTUM_BREAK_Ep_1A.ism").write_text("old", encoding="utf-8")
        with self.assertLogs("quantumfetcher.episodes", "WARNING"):
            self.download(self.tracks("500000", "esmx"))
        self.assertEqual(list(self.folder.glob("*.ism")), [self.folder / "J1A.ism"])
        self.assertTrue((self.folder / "QUANTUM_BREAK_Ep_1A.ism.old").exists())

    def test_leaves_episodes_without_video_and_audio_to_stream(self):
        self.download(self.tracks("enus_captions", "esmx"))
        self.assertEqual(
            files(self.folder), ["J1A_enus_captions_256000.ismt", "J1A_esmx_256000.isma"]
        )

    def test_keeps_tracks_already_downloaded(self):
        self.folder.mkdir()
        (self.folder / "J1A_esmx_256000.isma").write_bytes(b"kept")
        self.download(self.tracks("esmx", "enus_captions"))
        self.assertEqual((self.folder / "J1A_esmx_256000.isma").read_bytes(), b"kept")
        self.assertFalse(any("esmx" in url for url in self.client.requests[1:]))

    def test_saves_subtitles_with_the_episode_title(self):
        self.download(self.tracks("enus"), extract_subtitles=True, episode_title=True)
        self.assertEqual(
            (self.folder / "enus_captions.srt").read_bytes(),
            b"1\r\n00:00:00,500 --> 00:00:01,500\r\nenus_captions 0\r\n\r\n"
            b"2\r\n00:00:02,500 --> 00:00:03,500\r\nenus_captions 1\r\n\r\n"
            b"3\r\n00:00:04,500 --> 00:00:05,500\r\nenus_captions 2\r\n\r\n"
            b"4\r\n00:00:07,500 --> 00:00:09,833\r\nEPISODE 1: Monarch Solutions\r\n",
        )

    def test_reports_the_episodes_that_fail_and_carries_on(self):
        broken = Episode("J1B", self.episode.manifest)
        del self.client.responses[self.tracks("2000000")[0].fragment_url(0)]
        downloader = EpisodeDownloader(
            TrackDownloader(self.client, 2), self.root, Progress(disable=True)
        )
        plan = [(broken, self.tracks("best")), (self.episode, self.tracks("500000"))]
        with self.assertLogs("quantumfetcher.episodes", "ERROR") as logs:
            self.assertEqual(downloader.download_all(plan), ["J1B"])
        self.assertIn("Could not download J1B: 404", logs.output[0])
        self.assertIn("J1A_video_500000.ismv", files(self.folder))
        self.assertIn("J1B_video_2000000.ismv.part", files(self.root / "J1B"))

    def test_fetch_episodes_skips_the_ones_that_are_unavailable(self):
        videos = {"J1A": MANIFEST_URL, "J2A": "http://cdn.test/J2A.ism/manifest"}
        with self.assertLogs("quantumfetcher.episodes", "WARNING") as logs:
            episodes = fetch_episodes(self.client, videos, 2, Progress(disable=True))
        self.assertEqual([episode.id for episode in episodes], ["J1A"])
        self.assertIn("Skipping J2A: 404", logs.output[0])


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from quantumfetcher import videolist
from quantumfetcher.cli import app
from quantumfetcher.network import HttpClient
from support import MANIFEST_URL, FakeClient, episode_responses

MISSING_URL = "http://cdn.test/J2A.ism/manifest"


class CliTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.game = Path(directory.name).resolve() / "QuantumBreak"
        (self.game / "data").mkdir(parents=True)
        self.videolist = self.game / "data" / "videoList.rmdj"
        self.videolist.write_bytes(videolist.encode({"J1A": MANIFEST_URL, "J2A": MISSING_URL}))
        self.episodes = self.game / "videos" / "episodes"
        self.client = FakeClient(episode_responses())

    def run_cli(self, *arguments):
        get = lambda _, url: self.client.get(url)  # noqa: E731
        with patch.object(HttpClient, "get", get):
            return CliRunner().invoke(app, [str(argument) for argument in arguments])

    def test_downloads_the_default_tracks_of_the_episodes_given(self):
        result = self.run_cli("download", self.game, "--episodes", "j1a", "--yes")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn(f"Downloaded 1 episode to {self.episodes}", result.output)
        self.assertEqual(
            sorted(path.name for path in (self.episodes / "J1A").iterdir()),
            [
                "J1A.ism",
                "J1A.ismc",
                "J1A_enus_256000.isma",
                "J1A_enus_captions_256000.ismt",
                "J1A_video_2000000.ismv",
            ],
        )

    def test_downloads_from_the_original_list_once_it_is_patched(self):
        videolist.patch(self.videolist, "127.0.0.1:1")
        result = self.run_cli(
            "download",
            self.game,
            "-e",
            "J1A",
            "--video",
            "none",
            "--audio",
            "esmx",
            "--text",
            "none",
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue((self.episodes / "J1A" / "J1A_esmx_256000.isma").exists())

    def test_skips_episodes_whose_manifest_is_unavailable(self):
        result = self.run_cli("download", self.game, "-e", "all", "--video", "500000", "-y")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Skipping J2A", result.output)
        self.assertIn("Downloaded 1 episode", result.output)

    def test_fails_when_an_episode_cannot_be_downloaded(self):
        del self.client.responses[next(url for url in self.client.responses if "video=0" in url)]
        result = self.run_cli("download", self.game, "-e", "J1A", "--video", "all", "-y")
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("Error: Could not download 1 of 1 episode: J1A", result.output)

    def test_rejects_what_matches_nothing(self):
        cases = [
            (["-e", "J9Z"], "The video list has no episode J9Z"),
            (["-e", "J1A", "--audio", "pl"], "No audio track matches pl"),
            (
                ["-e", "J1A", "--video", "none", "--audio", "none", "--text", "none"],
                "pick no tracks",
            ),
            (["-e", "J2A"], "No episode could be fetched"),
        ]
        for arguments, error in cases:
            with self.subTest(arguments=arguments):
                result = self.run_cli("download", self.game, *arguments, "-y")
                self.assertEqual(result.exit_code, 1, result.output)
                self.assertIn(error, result.output)

    def test_needs_the_game_folder_unless_both_paths_are_given(self):
        result = self.run_cli("download", "-e", "J1A", "-y")
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("Error: Give the game folder", result.output)
        output = self.game / "elsewhere"
        result = self.run_cli(
            "download", "--videolist-path", self.videolist, "--episodes-path", output,
            "-e", "J1A", "--video", "none", "--text", "none",
        )  # fmt: skip
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue((output / "J1A" / "J1A_enus_256000.isma").exists())

    def test_formats_lists_the_tracks_and_their_selectors(self):
        result = self.run_cli("formats", self.game, "-e", "J1A")
        self.assertEqual(result.exit_code, 0, result.output)
        for selector in ("2000000", "500000", "enus", "esmx", "enus_captions", "eses_captions"):
            self.assertIn(selector, result.output)

    def test_videolist_dump_prints_or_saves_the_list(self):
        result = self.run_cli("videolist", "dump", self.game)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(json.loads(result.stdout), {"J1A": MANIFEST_URL, "J2A": MISSING_URL})
        output = self.game / "list.json"
        result = self.run_cli("videolist", "dump", "--videolist-path", self.videolist, "-o", output)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["J1A"], MANIFEST_URL)

    def test_videolist_patch_keeps_the_original_list(self):
        result = self.run_cli("videolist", "patch", self.game, "-s", "127.0.0.1:5000")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Pointed 2 episodes at http://127.0.0.1:5000", result.output)
        self.assertEqual(
            videolist.load(self.videolist)["J1A"], "http://127.0.0.1:5000/J1A/manifest"
        )
        original = videolist.load(videolist.original_path(self.videolist))
        self.assertEqual(original, {"J1A": MANIFEST_URL, "J2A": MISSING_URL})

    def test_videolist_build_saves_the_list_episodes_are_read_from(self):
        built = {"J3A": "http://cdn.test/J3A.ism/manifest"}
        source = self.game / "list.json"
        source.write_text(json.dumps(built), encoding="utf-16")
        for patched in (False, True):
            with self.subTest(patched=patched):
                if patched:
                    self.run_cli("videolist", "patch", self.game)
                result = self.run_cli("videolist", "build", source, self.game)
                self.assertEqual(result.exit_code, 0, result.output)
                dumped = self.run_cli("videolist", "dump", self.game)
                self.assertEqual(json.loads(dumped.stdout), built)
                original = videolist.original_path(self.videolist)
                self.assertEqual(original.exists(), patched)

    def test_reports_broken_video_lists(self):
        self.videolist.write_bytes(b"broken")
        result = self.run_cli("videolist", "dump", self.game)
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("Error:", result.output)
        self.assertIn("videoList.rmdj", result.output)


if __name__ == "__main__":
    unittest.main()

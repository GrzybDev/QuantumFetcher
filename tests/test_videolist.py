import json
import tempfile
import unittest
from pathlib import Path

from quantumfetcher import videolist
from quantumfetcher.errors import FetchError
from support import encrypt

GAME_LIST = (
    b'{\r\n\t"J1 - 4K Test" : "http://a.test/J1A%20-%204K%20Test.ism/manifest?tkn=1",\r\n'
    b'\t"J1A" : "http://a.test/J1A.ism/manifest?tkn=1",\r\n\t\r\n'
    b'\t"J2A" : "http://a.test/J2A.ism/manifest?tkn=1"\r\n}\r\n'
)


class VideoListTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "videoList.rmdj"
        self.path.write_bytes(encrypt(GAME_LIST))

    def test_decodes_the_games_own_list(self):
        self.assertEqual(
            videolist.load(self.path),
            {
                "J1 - 4K Test": "http://a.test/J1A%20-%204K%20Test.ism/manifest?tkn=1",
                "J1A": "http://a.test/J1A.ism/manifest?tkn=1",
                "J2A": "http://a.test/J2A.ism/manifest?tkn=1",
            },
        )

    def test_encodes_what_it_decodes(self):
        videos = videolist.load(self.path)
        self.assertEqual(videolist.decode(videolist.encode(videos)), videos)
        self.assertEqual(encrypt(videolist.encode(videos)), json.dumps(videos, indent=4).encode())

    def test_rejects_files_that_are_not_video_lists(self):
        for data in (encrypt(b"[]"), encrypt(b'{"J1A": 1}'), encrypt(b"{"), b"\xff\xfe"):
            with self.subTest(data=data):
                self.path.write_bytes(data)
                with self.assertRaisesRegex(FetchError, "videoList.rmdj"):
                    videolist.load(self.path)

    def test_patch_points_every_episode_at_the_server_and_keeps_the_original(self):
        videolist.patch(self.path, "127.0.0.1:1234")
        self.assertEqual(
            videolist.load(self.path),
            {
                "J1 - 4K Test": "http://127.0.0.1:1234/J1 - 4K Test/manifest",
                "J1A": "http://127.0.0.1:1234/J1A/manifest",
                "J2A": "http://127.0.0.1:1234/J2A/manifest",
            },
        )
        self.assertEqual(self.original().read_bytes(), encrypt(GAME_LIST))

    def test_patching_again_starts_from_the_original(self):
        videolist.patch(self.path, "127.0.0.1:1234")
        videolist.patch(self.path, "10.0.0.1:80")
        self.assertEqual(videolist.load(self.path)["J1A"], "http://10.0.0.1:80/J1A/manifest")
        self.assertEqual(self.original().read_bytes(), encrypt(GAME_LIST))

    def test_unpatched_prefers_the_kept_original(self):
        self.assertEqual(videolist.unpatched(self.path), self.path)
        videolist.patch(self.path, "127.0.0.1:1234")
        self.assertEqual(videolist.unpatched(self.path), self.original())

    def test_read_json_reads_what_windows_tools_write(self):
        source = self.path.with_name("list.json")
        for encoding in ("utf-8",):
            with self.subTest(encoding=encoding):
                source.write_text('{"J1A": "http://a.test/manifest"}', encoding=encoding)
                self.assertEqual(videolist.read_json(source), {"J1A": "http://a.test/manifest"})

    def test_read_json_names_the_file_with_the_problem(self):
        source = self.path.with_name("list.json")
        for text in ('{"J1A": ["http://a.test"]}', "{"):
            with self.subTest(text=text):
                source.write_text(text, encoding="utf-8")
                with self.assertRaisesRegex(FetchError, "list.json"):
                    videolist.read_json(source)

    def original(self):
        return self.path.with_name("videoList_original.rmdj")


if __name__ == "__main__":
    unittest.main()

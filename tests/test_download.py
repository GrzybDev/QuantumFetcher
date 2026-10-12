import tempfile
import threading
import time
import unittest
from contextlib import closing
from pathlib import Path

from quantumfetcher.concurrency import completed_in_order
from quantumfetcher.download import TrackDownloader
from quantumfetcher.errors import FetchError
from quantumfetcher.manifest import ClientManifest
from quantumfetcher.mp4 import TrackWriter, read_fragments
from support import MANIFEST_URL, FakeClient, client_manifest, episode_responses


class TrackDownloaderTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "J1A_enus_256000.isma"
        manifest = ClientManifest.parse(MANIFEST_URL, client_manifest(chunks=6))
        self.track = next(track for track in manifest.tracks if track.name == "enus")
        self.urls = [self.track.fragment_url(start) for start in self.track.start_times]
        self.client = FakeClient(episode_responses(chunks=6))

    def media(self):
        with self.path.open("rb") as file:
            return [data.decode() for _, data in read_fragments(file)]

    def test_writes_the_fragments_in_manifest_order(self):
        class SlowFirstClient(FakeClient):
            def get(self, url):
                # The earliest fragments arrive last.
                time.sleep(0.01 * (6 - len(self.requests)))
                return super().get(url)

        sizes = []
        TrackDownloader(SlowFirstClient(self.client.responses), 4).download(
            self.track, self.path, sizes.append
        )
        self.assertEqual(self.media(), self.urls)
        self.assertEqual(sizes[0], 0)
        self.assertEqual(sum(sizes[1:]), sum(len(self.client.responses[url]) for url in self.urls))

    def test_carries_on_from_a_partial_download(self):
        with self.partial().open("w+b") as file:
            writer = TrackWriter(file, self.track)
            for url in self.urls[:2]:
                writer.append(self.client.responses[url])
            kept = writer.size
        sizes = []
        TrackDownloader(self.client, 2).download(self.track, self.path, sizes.append)
        self.assertCountEqual(self.client.requests, self.urls[2:])
        self.assertEqual(sizes[0], kept)
        self.assertEqual(self.media(), self.urls)
        self.assertFalse(self.partial().exists())

    def test_keeps_the_partial_download_when_a_fragment_fails(self):
        del self.client.responses[self.urls[3]]
        with self.assertRaisesRegex(FetchError, "Not Found"):
            TrackDownloader(self.client, 2).download(self.track, self.path, lambda size: None)
        self.assertFalse(self.path.exists())
        with self.partial().open("r+b") as file:
            self.assertEqual(TrackWriter(file, self.track).fragments, 3)

    def partial(self):
        return self.path.with_name(f"{self.path.name}.part")


class CompletedInOrderTests(unittest.TestCase):
    def test_yields_in_item_order_however_calls_finish(self):
        def call(number):
            time.sleep(0.01 * (5 - number))
            return number

        with closing(completed_in_order(call, range(5), 5)) as futures:
            self.assertEqual([future.result() for future in futures], [0, 1, 2, 3, 4])

    def test_runs_few_items_ahead_and_cancels_the_rest_when_closed(self):
        started = []
        release = threading.Event()

        def call(number):
            started.append(number)
            release.wait(5)
            return number

        futures = completed_in_order(call, range(100), 2)
        release.set()
        self.assertEqual(next(futures).result(), 0)
        futures.close()
        time.sleep(0.05)
        self.assertLessEqual(len(started), 6)

    def test_passes_on_what_a_call_raises(self):
        def call(number):
            if number == 1:
                raise FetchError("broken")
            return number

        with closing(completed_in_order(call, range(3), 2)) as futures:
            results = list(futures)
        self.assertEqual(results[0].result(), 0)
        with self.assertRaisesRegex(FetchError, "broken"):
            results[1].result()


if __name__ == "__main__":
    unittest.main()

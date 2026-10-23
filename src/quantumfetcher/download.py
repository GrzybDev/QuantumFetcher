from collections.abc import Callable
from pathlib import Path

from quantumfetcher.concurrency import results_in_order
from quantumfetcher.manifest import Track
from quantumfetcher.mp4 import TrackWriter
from quantumfetcher.network import HttpClient


class TrackDownloader:
    def __init__(self, client: HttpClient, workers: int) -> None:
        self._client = client
        self._workers = workers

    def download(self, track: Track, path: Path, progress: Callable[[int], None]) -> None:
        """Download a track through a .part file, so that a file at `path` is always whole.

        The .part file an interrupted download left is carried on from its last whole fragment.

        Args:
            track: The track to download.
            path: The file to save it to.
            progress: Called with the bytes each step adds, starting with those already kept.
        """
        partial = path.with_name(f"{path.name}.part")
        with partial.open("r+b" if partial.exists() else "w+b") as file:
            writer = TrackWriter(file, track)
            progress(writer.size)
            urls = map(track.fragment_url, track.start_times[writer.fragments :])
            with results_in_order(self._client.get, urls, self._workers) as fragments:
                for fragment in fragments:
                    writer.append(fragment)
                    progress(len(fragment))
            writer.finish()
        partial.replace(path)

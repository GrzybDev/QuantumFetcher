from collections.abc import Callable
from contextlib import closing
from pathlib import Path

from quantumfetcher.concurrency import completed_in_order
from quantumfetcher.manifest import Track
from quantumfetcher.mp4 import TrackWriter
from quantumfetcher.network import HttpClient


class TrackDownloader:
    def __init__(self, client: HttpClient, workers: int) -> None:
        self._client = client
        self._workers = workers

    def download(self, track: Track, path: Path, progress: Callable[[int], None]) -> None:
        """Download `track` into `path`, resuming the .part file an interrupted download left,
        so that a file at `path` is always whole. `progress` gets the bytes each step adds."""
        partial = path.with_name(f"{path.name}.part")
        with partial.open("r+b" if partial.exists() else "w+b") as file:
            writer = TrackWriter(file, track)
            progress(writer.size)
            urls = map(track.fragment_url, track.start_times[writer.fragments :])
            with closing(completed_in_order(self._client.get, urls, self._workers)) as fetched:
                for future in fetched:
                    fragment = future.result()
                    writer.append(fragment)
                    progress(len(fragment))
            writer.finish()
        partial.replace(path)

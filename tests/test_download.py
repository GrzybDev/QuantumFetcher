import threading
import time
from contextlib import closing
from pathlib import Path

import pytest

from quantumfetcher.concurrency import completed_in_order
from quantumfetcher.download import TrackDownloader
from quantumfetcher.errors import FetchError
from quantumfetcher.manifest import ClientManifest
from quantumfetcher.mp4 import TrackWriter, read_fragments
from support import MANIFEST_URL, FakeClient, client_manifest, episode_responses

ENUS = next(
    track
    for track in ClientManifest.parse(MANIFEST_URL, client_manifest(chunks=6)).tracks
    if track.name == "enus"
)
URLS = [ENUS.fragment_url(start) for start in ENUS.start_times]
RESPONSES = episode_responses(chunks=6)


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / "J1A_enus_256000.isma"


def partial(path: Path) -> Path:
    return path.with_name(f"{path.name}.part")


def media(path: Path) -> list[str]:
    with path.open("rb") as file:
        return [data.decode() for _, data in read_fragments(file)]


def test_writes_the_fragments_in_manifest_order(path: Path) -> None:
    class SlowFirstClient(FakeClient):
        def get(self, url: str) -> bytes:
            # The earliest fragments arrive last.
            time.sleep(0.01 * (6 - len(self.requests)))
            return super().get(url)

    sizes: list[int] = []
    TrackDownloader(SlowFirstClient(RESPONSES), 4).download(ENUS, path, sizes.append)
    assert media(path) == URLS
    assert sizes[0] == 0
    assert sum(sizes[1:]) == sum(len(RESPONSES[url]) for url in URLS)


def test_carries_on_from_a_partial_download(path: Path) -> None:
    with partial(path).open("w+b") as file:
        writer = TrackWriter(file, ENUS)
        for url in URLS[:2]:
            writer.append(RESPONSES[url])
        kept = writer.size
    client = FakeClient(RESPONSES)
    sizes: list[int] = []
    TrackDownloader(client, 2).download(ENUS, path, sizes.append)
    assert sorted(client.requests) == sorted(URLS[2:])
    assert sizes[0] == kept
    assert media(path) == URLS
    assert not partial(path).exists()


def test_keeps_the_partial_download_when_a_fragment_fails(path: Path) -> None:
    client = FakeClient(RESPONSES)
    del client.responses[URLS[3]]
    with pytest.raises(FetchError, match="Not Found"):
        TrackDownloader(client, 2).download(ENUS, path, lambda size: None)
    assert not path.exists()
    with partial(path).open("r+b") as file:
        assert TrackWriter(file, ENUS).fragments == 3


def test_completed_in_order_yields_in_item_order_however_calls_finish() -> None:
    def call(number: int) -> int:
        time.sleep(0.01 * (5 - number))
        return number

    with closing(completed_in_order(call, range(5), 5)) as futures:
        assert [future.result() for future in futures] == [0, 1, 2, 3, 4]


def test_completed_in_order_runs_few_items_ahead_and_cancels_the_rest_when_closed() -> None:
    started: list[int] = []
    release = threading.Event()

    def call(number: int) -> int:
        started.append(number)
        release.wait(5)
        return number

    futures = completed_in_order(call, range(100), 2)
    release.set()
    assert next(futures).result() == 0
    futures.close()
    time.sleep(0.05)
    assert len(started) <= 6


def test_completed_in_order_passes_on_what_a_call_raises() -> None:
    def call(number: int) -> int:
        if number == 1:
            raise FetchError("broken")
        return number

    with closing(completed_in_order(call, range(3), 2)) as futures:
        results = list(futures)
    assert results[0].result() == 0
    with pytest.raises(FetchError, match="broken"):
        results[1].result()

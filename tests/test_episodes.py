from collections.abc import Sequence
from pathlib import Path

import pytest
from rich.progress import Progress

from quantumfetcher import selection
from quantumfetcher.download import TrackDownloader
from quantumfetcher.episodes import Episode, EpisodeDownloader
from quantumfetcher.manifest import Track
from support import FakeClient, episode_manifest, episode_responses, files, served_locally

EPISODE = Episode("J1A", episode_manifest())


@pytest.fixture
def client() -> FakeClient:
    return FakeClient(episode_responses())


def tracks(*selectors: str) -> list[Track]:
    return selection.select(EPISODE.manifest.tracks, selectors)


def download(
    client: FakeClient,
    root: Path,
    plan: Sequence[tuple[Episode, Sequence[Track]]],
    **options: bool,
) -> list[str]:
    downloader = TrackDownloader(client, 2)
    return EpisodeDownloader(downloader, root, Progress(disable=True), **options).download_all(plan)


def test_saves_tracks_with_manifests_quantumstreamer_plays_offline(
    client: FakeClient, tmp_path: Path
) -> None:
    assert download(client, tmp_path, [(EPISODE, tracks("500000", "esmx", "enus_captions"))]) == []
    assert files(tmp_path / "J1A") == [
        "J1A.ism",
        "J1A.ismc",
        "J1A_enus_captions_256000.ismt",
        "J1A_esmx_256000.isma",
        "J1A_video_500000.ismv",
    ]
    assert served_locally(tmp_path / "J1A") == (9, 0)


def test_manifests_offer_the_tracks_of_earlier_downloads(
    client: FakeClient, tmp_path: Path
) -> None:
    download(client, tmp_path, [(EPISODE, tracks("enus_captions"))])
    download(client, tmp_path, [(EPISODE, tracks("500000", "esmx"))])
    assert served_locally(tmp_path / "J1A") == (9, 0)


def test_moves_aside_server_manifests_quantumstreamer_could_use_instead(
    client: FakeClient, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    folder = tmp_path / "J1A"
    folder.mkdir()
    (folder / "QUANTUM_BREAK_Ep_1A.ism").write_text("old", encoding="utf-8")
    download(client, tmp_path, [(EPISODE, tracks("500000", "esmx"))])
    assert list(folder.glob("*.ism")) == [folder / "J1A.ism"]
    assert (folder / "QUANTUM_BREAK_Ep_1A.ism.old").exists()
    assert "Renamed QUANTUM_BREAK_Ep_1A.ism to QUANTUM_BREAK_Ep_1A.ism.old" in caplog.text


def test_leaves_episodes_without_video_and_audio_to_stream(
    client: FakeClient, tmp_path: Path
) -> None:
    download(client, tmp_path, [(EPISODE, tracks("enus_captions", "esmx"))])
    assert files(tmp_path / "J1A") == ["J1A_enus_captions_256000.ismt", "J1A_esmx_256000.isma"]


def test_keeps_tracks_already_downloaded(client: FakeClient, tmp_path: Path) -> None:
    folder = tmp_path / "J1A"
    folder.mkdir()
    (folder / "J1A_esmx_256000.isma").write_bytes(b"kept")
    download(client, tmp_path, [(EPISODE, tracks("esmx", "enus_captions"))])
    assert (folder / "J1A_esmx_256000.isma").read_bytes() == b"kept"
    assert not any("esmx" in url for url in client.requests)


def test_saves_subtitles_with_the_episode_title(client: FakeClient, tmp_path: Path) -> None:
    download(
        client,
        tmp_path,
        [(EPISODE, tracks("enus"))],
        extract_subtitles=True,
        episode_title=True,
    )
    assert (tmp_path / "J1A" / "enus_captions.srt").read_bytes() == (
        b"1\r\n00:00:00,500 --> 00:00:01,500\r\nenus_captions 0\r\n\r\n"
        b"2\r\n00:00:02,500 --> 00:00:03,500\r\nenus_captions 1\r\n\r\n"
        b"3\r\n00:00:04,500 --> 00:00:05,500\r\nenus_captions 2\r\n\r\n"
        b"4\r\n00:00:07,500 --> 00:00:09,833\r\nEPISODE 1: Monarch Solutions\r\n"
    )


def test_keeps_subtitles_that_may_be_edited(client: FakeClient, tmp_path: Path) -> None:
    srt = tmp_path / "J1A" / "enus_captions.srt"
    srt.parent.mkdir()
    srt.write_text("edited", encoding="utf-8")
    download(client, tmp_path, [(EPISODE, tracks("enus_captions"))], extract_subtitles=True)
    assert srt.read_text(encoding="utf-8") == "edited"


def test_reports_the_episodes_that_fail_and_carries_on(
    client: FakeClient, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    del client.responses[tracks("2000000")[0].fragment_url(0)]
    plan = [(Episode("J1B", EPISODE.manifest), tracks("best")), (EPISODE, tracks("500000"))]
    assert download(client, tmp_path, plan) == ["J1B"]
    assert "Could not download J1B: 404" in caplog.text
    assert "J1A_video_500000.ismv" in files(tmp_path / "J1A")
    assert "J1B_video_2000000.ismv.part" in files(tmp_path / "J1B")

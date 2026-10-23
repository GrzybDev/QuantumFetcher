import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from rich.filesize import decimal
from rich.progress import Progress

from quantumfetcher import subtitles
from quantumfetcher.concurrency import results_in_order
from quantumfetcher.download import TrackDownloader
from quantumfetcher.errors import FetchError
from quantumfetcher.manifest import ClientManifest, StreamType, Track, server_manifest
from quantumfetcher.network import HttpClient

log = logging.getLogger(__name__)

_EXTENSIONS = {StreamType.VIDEO: ".ismv", StreamType.AUDIO: ".isma", StreamType.TEXT: ".ismt"}


@dataclass(frozen=True)
class Episode:
    id: str
    manifest: ClientManifest


@dataclass(frozen=True)
class EpisodeFolder:
    """The folder named after an episode, where QuantumStreamer looks for the episode's files."""

    root: Path
    episode_id: str

    @property
    def path(self) -> Path:
        return self.root / self.episode_id

    @property
    def client_manifest(self) -> Path:
        return self.path / f"{self.episode_id}.ismc"

    @property
    def server_manifest(self) -> Path:
        return self.path / f"{self.episode_id}.ism"

    def track(self, track: Track) -> Path:
        name = f"{self.episode_id}_{track.name}_{track.bitrate}{_EXTENSIONS[track.type]}"
        return self.path / name

    def subtitles(self, track: Track) -> Path:
        return self.path / f"{track.name}.srt"


def fetch_episodes(
    client: HttpClient, videos: Mapping[str, str], workers: int, progress: Progress
) -> list[Episode]:
    """Fetch the episodes' manifests, skipping with a warning each one that cannot be fetched.

    Args:
        client: The client to fetch with.
        videos: The manifest URL of each episode ID.
        workers: The number of manifests to fetch at once.
        progress: The progress display to show a task on.

    Returns:
        The episodes whose manifests were fetched, in the order of `videos`.
    """
    task = progress.add_task("Fetching manifests", total=len(videos))
    episodes = []
    fetch = partial(_fetch_manifest, client)
    with results_in_order(fetch, videos.values(), workers) as manifests:
        for episode_id, manifest in zip(videos, manifests, strict=True):
            if isinstance(manifest, FetchError):
                log.warning("Skipping %s: %s", episode_id, manifest)
            else:
                episodes.append(Episode(episode_id, manifest))
            progress.advance(task)
    return episodes


class EpisodeDownloader:
    def __init__(
        self,
        downloader: TrackDownloader,
        root: Path,
        progress: Progress,
        *,
        extract_subtitles: bool = False,
        episode_title: bool = False,
    ) -> None:
        self._downloader = downloader
        self._root = root
        self._progress = progress
        self._extract_subtitles = extract_subtitles
        self._episode_title = episode_title

    def download_all(self, plan: Sequence[tuple[Episode, Sequence[Track]]]) -> list[str]:
        """Download each episode's tracks, returning the IDs of the episodes that failed."""
        failed = []
        for number, (episode, tracks) in enumerate(plan, 1):
            log.info("Episode %s (%d of %d)", episode.id, number, len(plan))
            try:
                self.download(episode, tracks)
            except (FetchError, OSError) as error:
                log.error("Could not download %s: %s", episode.id, error)
                failed.append(episode.id)
        return failed

    def download(self, episode: Episode, tracks: Sequence[Track]) -> None:
        folder = EpisodeFolder(self._root, episode.id)
        folder.path.mkdir(parents=True, exist_ok=True)
        for track in tracks:
            self._download_track(f"{episode.id} {track.label}", track, folder.track(track))
        # The manifests offer every track in the folder, also those of earlier downloads, and
        # replace the server's, so they need something to play.
        present = [track for track in episode.manifest.tracks if folder.track(track).exists()]
        if {StreamType.VIDEO, StreamType.AUDIO} <= {track.type for track in present}:
            self._write_manifests(episode, present, folder)
        else:
            log.info(
                "Leaving %s to stream, as playing it offline needs video and audio", episode.id
            )
        if self._extract_subtitles:
            for track in tracks:
                if track.type is StreamType.TEXT:
                    self._save_subtitles(episode, track, folder)

    def _download_track(self, label: str, track: Track, path: Path) -> None:
        if path.exists():
            log.info("Keeping %s", path.name)
            return
        task = self._progress.add_task(label, total=track.estimated_size)
        try:
            self._downloader.download(track, path, partial(self._progress.advance, task))
        finally:
            self._progress.remove_task(task)
        log.info("Downloaded %s (%s)", path.name, decimal(path.stat().st_size))

    def _write_manifests(
        self, episode: Episode, tracks: Sequence[Track], folder: EpisodeFolder
    ) -> None:
        # QuantumStreamer plays an episode from one server manifest, such as one an older version
        # of this tool wrote under another name.
        for other in folder.path.glob("*.ism"):
            if other != folder.server_manifest:
                other.replace(other.with_name(f"{other.name}.old"))
                log.warning(
                    "Renamed %s to %s.old, so QuantumStreamer does not play %s from it instead",
                    other.name,
                    other.name,
                    episode.id,
                )
        folder.client_manifest.write_bytes(episode.manifest.local_copy(tracks))
        files = [(track, folder.track(track).name) for track in tracks]
        folder.server_manifest.write_bytes(server_manifest(folder.client_manifest.name, files))
        log.info("Wrote %s and %s", folder.server_manifest.name, folder.client_manifest.name)

    def _save_subtitles(self, episode: Episode, track: Track, folder: EpisodeFolder) -> None:
        path = folder.subtitles(track)
        if path.exists():
            log.info("Keeping %s, as it may hold edited captions", path.name)
            return
        cues = subtitles.read_cues(folder.track(track), track.timescale)
        if self._episode_title and (title := subtitles.episode_title(episode.id)):
            cues.append(title)
        path.write_text(subtitles.to_srt(cues), encoding="utf-8", newline="\r\n")
        log.info("Saved %s", path.name)


def _fetch_manifest(client: HttpClient, url: str) -> ClientManifest | FetchError:
    # Returned rather than raised, as the first error raised would end the other fetches.
    try:
        return ClientManifest.parse(url, client.get(url))
    except FetchError as error:
        return error

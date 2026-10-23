import logging
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

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


@dataclass
class DownloadSummary:
    """What downloading episodes did.

    Attributes:
        saved: The track files saved.
        offline: The IDs of the episodes QuantumStreamer plays offline.
        failed: The IDs of the episodes that failed.
    """

    saved: list[Path] = field(default_factory=list)
    offline: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


def fetch_episodes(
    client: HttpClient, videos: Mapping[str, str], workers: int, progress: Callable[[], None]
) -> list[Episode]:
    """Fetch the episodes' manifests, skipping with a warning each one that cannot be fetched.

    Args:
        client: The client to fetch with.
        videos: The manifest URL of each episode ID.
        workers: The number of manifests to fetch at once.
        progress: Called once each manifest is fetched or skipped.

    Returns:
        The episodes whose manifests were fetched, in the order of `videos`.
    """
    episodes = []
    fetch = partial(_fetch_manifest, client)
    with results_in_order(fetch, videos.values(), workers) as manifests:
        for episode_id, manifest in zip(videos, manifests, strict=True):
            if isinstance(manifest, FetchError):
                log.warning("Skipping %s: %s", episode_id, manifest)
            else:
                episodes.append(Episode(episode_id, manifest))
            progress()
    return episodes


class EpisodeDownloader:
    def __init__(
        self,
        downloader: TrackDownloader,
        root: Path,
        progress: Callable[[str, int | None], AbstractContextManager[Callable[[int], None]]],
        *,
        extract_subtitles: bool = False,
        episode_title: bool = False,
    ) -> None:
        """Save episodes in the folders QuantumStreamer reads them from.

        Args:
            downloader: The downloader of each track.
            root: The folder holding a folder for each episode.
            progress: Given a track's label and estimated size, a context to show its download
                in, which gives the call that adds the bytes each step downloads.
            extract_subtitles: Whether to save the captions downloaded as SubRip files.
            episode_title: Whether to end the saved subtitles with the episode title.
        """
        self._downloader = downloader
        self._root = root
        self._progress = progress
        self._extract_subtitles = extract_subtitles
        self._episode_title = episode_title

    def download_all(self, plan: Sequence[tuple[Episode, Sequence[Track]]]) -> DownloadSummary:
        """Download the tracks of each episode, carrying on after an episode that fails.

        Args:
            plan: Each episode with the tracks of it to download.

        Returns:
            The track files saved and the episodes playable offline or failed.
        """
        summary = DownloadSummary()
        for number, (episode, tracks) in enumerate(plan, 1):
            log.info("Episode %s (%d of %d)", episode.id, number, len(plan))
            try:
                self._download(episode, tracks, summary)
            except (FetchError, OSError) as error:
                log.error("Could not download %s: %s", episode.id, error)
                summary.failed.append(episode.id)
        return summary

    def _download(
        self, episode: Episode, tracks: Sequence[Track], summary: DownloadSummary
    ) -> None:
        """Save an episode's tracks, manifests and subtitles, adding what it did to `summary`.

        Args:
            episode: The episode to save.
            tracks: The tracks of it to download.
            summary: The summary of the downloads so far.
        """
        folder = EpisodeFolder(self._root, episode.id)
        folder.path.mkdir(parents=True, exist_ok=True)
        for track in tracks:
            path = folder.track(track)
            if self._download_track(f"{episode.id} {track.label}", track, path):
                summary.saved.append(path)
        # The manifests offer every track in the folder, also those of earlier downloads, and
        # replace the server's, so they need something to play.
        present = [track for track in episode.manifest.tracks if folder.track(track).exists()]
        if {StreamType.VIDEO, StreamType.AUDIO} <= {track.type for track in present}:
            self._write_manifests(episode, present, folder)
            summary.offline.append(episode.id)
        else:
            log.info(
                "Leaving %s to stream, as playing it offline needs video and audio", episode.id
            )
        if self._extract_subtitles:
            for track in tracks:
                if track.type is StreamType.TEXT:
                    self._save_subtitles(episode, track, folder)

    def _download_track(self, label: str, track: Track, path: Path) -> bool:
        """Download a track unless its file exists, returning whether it did.

        Args:
            label: The track's name in the progress display.
            track: The track to download.
            path: The file to save it to.
        """
        if path.exists():
            log.info("Keeping %s", path.name)
            return False
        with self._progress(label, track.estimated_size) as advance:
            self._downloader.download(track, path, advance)
        log.info("Downloaded %s", path.name)
        return True

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

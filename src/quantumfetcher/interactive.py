from pathlib import Path

from rich.progress import track

from quantumfetcher.downloader import fetch_manifest
from quantumfetcher.enumerators.ManifestType import ManifestType
from quantumfetcher.videolist import VideoList


def InteractiveMain(gamePath: Path, videoList_path: Path):
    videoList = VideoList(gamePath / videoList_path)

    all_episodes = videoList.get_episode_list()

    # Prefetch server manifests for episodes
    manifests = {}
    for episode_id in track(
        all_episodes, description="Prefetching episode manifests..."
    ):
        manifest_url = videoList.get_manifest_url(episode_id)
        client_manifest = fetch_manifest(manifest_url, ManifestType.Client)
        server_manifest = fetch_manifest(manifest_url, ManifestType.Server)
        manifests[episode_id] = (server_manifest, client_manifest)

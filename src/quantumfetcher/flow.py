from rich.progress import Progress

from quantumfetcher.downloader import Downloader
from quantumfetcher.enumerators.type_manifest import ManifestType
from quantumfetcher.manifests.base import BaseManifest
from quantumfetcher.video_list import VideoList


class Flow:

    def __init__(self, interactive: bool, video_list: VideoList, **kwargs) -> None:
        self.__downloader = Downloader()

        self.__interactive = interactive
        self.__video_list = video_list

        self.__fetch_manifests()

    def __fetch_manifests(self):
        self.__manifests: dict[str, dict[ManifestType, BaseManifest]] = {}

        with Progress(transient=True) as progress:
            for episode_id, client_manifest_url in progress.track(
                self.__video_list.episode_list.items(),
                description="Fetching manifests...",
            ):
                server_manifest_url = self.__video_list.get_server_manifest_url(
                    episode_id
                )

                progress.console.log(
                    f"Fetching client manifest for episode {episode_id}..."
                )

                client_manifest = self.__downloader.fetch_manifest(
                    manifest_type=ManifestType.Client,
                    manifest_url=client_manifest_url,
                )

                progress.console.log(
                    f"Fetching server manifest for episode {episode_id}..."
                )

                server_manifest = self.__downloader.fetch_manifest(
                    manifest_type=ManifestType.Server,
                    manifest_url=server_manifest_url,
                )

                self.__manifests[episode_id] = {
                    ManifestType.Client: client_manifest,
                    ManifestType.Server: server_manifest,
                }

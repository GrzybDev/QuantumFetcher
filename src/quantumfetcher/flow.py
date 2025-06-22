from rich.progress import Progress

from quantumfetcher.downloader import Downloader
from quantumfetcher.enumerators.type_manifest import ManifestType
from quantumfetcher.manifests.base import BaseManifest
from quantumfetcher.prompt import Prompt
from quantumfetcher.video_list import VideoList


class Flow:

    def __init__(self, interactive: bool, video_list: VideoList, **kwargs) -> None:
        self.__downloader = Downloader()

        self.__interactive = interactive
        self.__video_list = video_list

        self.__episodes_to_fetch: list[str] | None = kwargs["episodes"]

        self.__fetch_manifests()

    def __fetch_manifests(self):
        self.__manifests: dict[str, dict[ManifestType, BaseManifest]] = {}

        episodes = self.__video_list.episode_list

        # If episodes to fetch is provided, filter the video list
        # Print warning if episodes specified are not in the video list
        if self.__episodes_to_fetch is not None:
            episodes = {
                episode_id: url
                for episode_id, url in episodes.items()
                if episode_id in self.__episodes_to_fetch
            }
        elif self.__interactive:
            self.__episodes_to_fetch = Prompt.select_episodes(self.__video_list)
            episodes = {
                episode_id: url
                for episode_id, url in episodes.items()
                if episode_id in self.__episodes_to_fetch
            }

        with Progress(transient=True) as progress:
            if self.__episodes_to_fetch:
                if len(episodes) != len(self.__episodes_to_fetch):
                    missing_episodes = set(self.__episodes_to_fetch) - set(episodes)
                    progress.console.log(
                        f"[yellow]Warning![/yellow] The following episodes are not in the video list: {missing_episodes}, they will be skipped."
                    )

            for episode_id, client_manifest_url in progress.track(
                episodes.items(),
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

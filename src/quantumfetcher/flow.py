from rich.progress import Progress

from quantumfetcher.downloader import Downloader
from quantumfetcher.enumerators.type_manifest import ManifestType
from quantumfetcher.enumerators.type_stream import StreamType
from quantumfetcher.helpers import deduplicate_streams, filter_streams, get_streams
from quantumfetcher.manifests.base import BaseManifest
from quantumfetcher.prompt import Prompt
from quantumfetcher.video_list import VideoList


class Flow:

    def __init__(self, interactive: bool, video_list: VideoList, **kwargs) -> None:
        self.__downloader = Downloader()

        self.__interactive = interactive
        self.__video_list = video_list

        self.__episodes_to_fetch: list[str] | None = kwargs["episodes"]

        self.__fetch_video_resolutions: list[str] | None = kwargs["video_resolutions"]
        self.__fetch_video_bitrates: list[str] | None = kwargs["video_bitrates"]
        self.__fetch_audio_langs: list[str] | None = kwargs["audio_langs"]
        self.__fetch_audio_bitrates: list[str] | None = kwargs["audio_bitrates"]
        self.__fetch_text_langs: list[str] | None = kwargs["text_langs"]
        self.__fetch_text_bitrates: list[str] | None = kwargs["text_bitrates"]

        self.__fetch_manifests()
        self.__prepare_streams()

    def __fetch_manifests(self):
        self.__manifests: dict[str, dict[ManifestType, BaseManifest]] = {}

        episodes = self.__video_list.episode_list

        # If episodes to fetch is provided, filter the video list
        # Print warning if episodes specified are not in the video list
        if self.__episodes_to_fetch is not None:
            if self.__episodes_to_fetch == ["all"]:
                self.__episodes_to_fetch = list(episodes.keys())
            else:
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

    def __prepare_streams(self):
        qualities = get_streams(self.__manifests)

        if self.__interactive:
            skip_video_prompt = (
                self.__fetch_video_resolutions is not None
                and self.__fetch_video_bitrates is not None
            )
            skip_audio_prompt = (
                self.__fetch_audio_langs is not None
                and self.__fetch_audio_bitrates is not None
            )
            skip_text_prompt = (
                self.__fetch_text_langs is not None
                and self.__fetch_text_bitrates is not None
            )
            answers = Prompt.select_streams(
                qualities,
                skip_video_prompt,
                skip_audio_prompt,
                skip_text_prompt,
            )
            self.__fetch_video_streams = answers.get(StreamType.Video, [])
            self.__fetch_audio_streams = answers.get(StreamType.Audio, [])
            self.__fetch_text_streams = answers.get(StreamType.Text, [])
            return

        # Video
        if (
            self.__fetch_video_resolutions is None
            and self.__fetch_video_bitrates is None
        ):
            video_streams = qualities[StreamType.Video][:1]
        else:
            video_streams = qualities[StreamType.Video]

            if self.__fetch_video_resolutions:
                if self.__fetch_video_resolutions == ["all"]:
                    pass
                else:
                    video_streams = [
                        v
                        for v in video_streams
                        if f"{v.height}p" in self.__fetch_video_resolutions
                    ]

            if self.__fetch_video_bitrates:
                if self.__fetch_video_bitrates == ["all"]:
                    pass
                else:
                    video_streams = [
                        v
                        for v in video_streams
                        if str(v.bitrate) in self.__fetch_video_bitrates
                    ]

        self.__fetch_video_streams = deduplicate_streams(
            video_streams, key_func=lambda x: x.height, reverse=True
        )

        # Audio
        if self.__fetch_audio_langs is None and self.__fetch_audio_bitrates is None:
            audio_streams = [
                a for a in qualities[StreamType.Audio] if a.language.name == "English"
            ][:1]
        else:
            audio_streams = filter_streams(
                qualities[StreamType.Audio],
                self.__fetch_audio_langs,
                self.__fetch_audio_bitrates,
                lang_attr="language",
                bitrate_attr="bitrate",
            )

        self.__fetch_audio_streams = deduplicate_streams(
            sorted(
                audio_streams,
                key=lambda x: (x.language.value, x.language.name, -x.bitrate),
            ),
            key_func=lambda x: (x.language.value, x.language.name),
        )

        # Text
        if self.__fetch_text_langs is None and self.__fetch_text_bitrates is None:
            text_streams = [
                t for t in qualities[StreamType.Text] if t.language.name == "English"
            ][:1]
        else:
            text_streams = filter_streams(
                qualities[StreamType.Text],
                self.__fetch_text_langs,
                self.__fetch_text_bitrates,
                lang_attr="language",
                bitrate_attr="bitrate",
            )
        self.__fetch_text_streams = deduplicate_streams(
            sorted(text_streams, key=lambda x: (x.name, -x.bitrate)),
            key_func=lambda x: x.name,
        )

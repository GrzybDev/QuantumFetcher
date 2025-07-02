import time
from math import ceil
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter, Retry
from requests.exceptions import ChunkedEncodingError
from rich.console import Group
from rich.live import Live
from rich.progress import (
    BarColumn,
    DownloadColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from quantumfetcher.constants import CHUNK_SIZE, USER_AGENT
from quantumfetcher.dataclasses.stream_audio import AudioStream
from quantumfetcher.dataclasses.stream_text import TextStream
from quantumfetcher.dataclasses.stream_video import VideoStream
from quantumfetcher.enumerators.type_manifest import ManifestType
from quantumfetcher.enumerators.type_stream import StreamType
from quantumfetcher.manifests.base import BaseManifest
from quantumfetcher.manifests.client import ClientManifest
from quantumfetcher.manifests.server import ServerManifest
from quantumfetcher.video_list import VideoList


class Downloader:

    __progress_overall = Progress(
        SpinnerColumn(finished_text="\u2713"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    )

    __progress_stream = Progress(
        SpinnerColumn(finished_text="\u2713"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
    )

    __progress_media = Progress(
        SpinnerColumn(finished_text="\u2713"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    )

    __progress_group = Group(__progress_overall, __progress_stream, __progress_media)

    def __init__(self):
        self.__session = requests.Session()
        self.__session.headers.update({"User-Agent": USER_AGENT})

        retries = Retry(total=10, backoff_factor=3)

        self.__session.mount("http://", HTTPAdapter(max_retries=retries))

    def __fetch_file(self, url: str) -> str:
        headers = self.__session.headers.copy()  # type: ignore
        headers["Accept-Encoding"] = "deflate"

        r = requests.get(url, headers=headers)
        r.raise_for_status()

        return r.content.decode()

    def fetch_manifest(
        self, manifest_type: ManifestType, manifest_url: str
    ) -> BaseManifest:
        content = self.__fetch_file(manifest_url)

        match manifest_type:
            case ManifestType.Client:
                return ClientManifest(content)
            case ManifestType.Server:
                return ServerManifest(content)

    def download(
        self,
        video_list: VideoList,
        manifests: dict[str, dict[ManifestType, BaseManifest]],
        episodes_path: Path,
        video_streams: list,
        audio_streams: list,
        text_streams: list,
    ):
        self.__video_list = video_list
        self.__manifests = manifests
        self.__download_path = episodes_path
        self.__streams_video = video_streams
        self.__streams_audio = audio_streams
        self.__streams_text = text_streams

        with Live(self.__progress_group, refresh_per_second=10):
            task_id = self.__progress_overall.add_task(
                "Downloading episodes...",
                total=len(manifests),
            )

            for episode_id, _ in manifests.items():
                self.__download_episode(episode_id)
                self.__progress_overall.update(task_id, advance=1)

    def __get_episode_manifests(
        self, episode_id
    ) -> tuple[ClientManifest, ServerManifest]:
        episode_manifests = self.__manifests[episode_id]
        client_manifest = episode_manifests[ManifestType.Client]

        if not isinstance(client_manifest, ClientManifest):
            raise TypeError(
                f"Expected ClientManifest for episode {episode_id}, got {type(client_manifest)}"
            )

        server_manifest = episode_manifests[ManifestType.Server]
        if not isinstance(server_manifest, ServerManifest):
            raise TypeError(
                f"Expected ServerManifest for episode {episode_id}, got {type(server_manifest)}"
            )

        return client_manifest, server_manifest

    def __download_episode(self, episode_id):
        episode_path = self.__download_path / episode_id
        episode_path.mkdir(exist_ok=True, parents=True)

        media_to_download, chunks_per_type = self.__get_streams_to_fetch(episode_id)

        streams_to_download = []
        for _, streams in media_to_download.items():
            streams_to_download.extend(streams)

        client_manifest, server_manifest = self.__get_episode_manifests(episode_id)
        client_manifest_path = server_manifest.get_client_manifest_path()

        if client_manifest_path is None:
            self.__progress_stream.console.log(
                f"[red]Error:[/red] Client manifest path not found for episode {episode_id}."
            )
            return

        task_id = self.__progress_stream.add_task(
            f"Downloading episode files for {episode_id}...",
            total=len(streams_to_download),
        )

        for stream in streams_to_download:
            stream_type = None
            if isinstance(stream, VideoStream):
                chunks = chunks_per_type[StreamType.Video]
                stream_type = StreamType.Video
            elif isinstance(stream, AudioStream):
                chunks = chunks_per_type[StreamType.Audio]
                stream_type = StreamType.Audio
            elif isinstance(stream, TextStream):
                chunks = chunks_per_type[StreamType.Text]
                stream_type = StreamType.Text
            else:
                raise TypeError(
                    f"Unknown stream type {type(stream)} for episode {episode_id}."
                )

            self.__download_stream(
                episode_id,
                episode_path,
                stream,
                stream_type,
                chunks,
            )

            self.__progress_stream.update(task_id, advance=1)

        for media_task in self.__progress_media.tasks:
            self.__progress_media.remove_task(media_task.id)

        self.__progress_stream.remove_task(task_id)

    def __get_streams_to_fetch(self, episode_id):
        client_manifest, _ = self.__get_episode_manifests(episode_id)

        media = {}
        chunks = {}

        def filter_streams(streams, stream_type):
            filtered_streams = []

            if stream_type == StreamType.Video:
                wanted_bitrates = [s.bitrate for s in self.__streams_video]
                for target in wanted_bitrates:
                    candidates = [
                        stream for stream in streams if stream.bitrate <= target
                    ]

                    if candidates:
                        best = max(candidates, key=lambda s: s.bitrate)

                        if best not in filtered_streams:
                            filtered_streams.append(best)
            elif stream_type == StreamType.Audio:
                wanted_bitrates = [s.bitrate for s in self.__streams_audio]
                wanted_languages = [s.language for s in self.__streams_audio]
                for lang in wanted_languages:
                    for target in wanted_bitrates:
                        candidates = [
                            stream
                            for stream in streams
                            if stream.language == lang and stream.bitrate <= target
                        ]

                        if candidates:
                            best = max(candidates, key=lambda s: s.bitrate)

                            if best not in filtered_streams:
                                filtered_streams.append(best)
            elif stream_type == StreamType.Text:
                wanted_languages = [s.language for s in self.__streams_text]
                for lang in wanted_languages:
                    candidates = [
                        stream for stream in streams if stream.language == lang
                    ]

                    if candidates:
                        best = candidates[0]

                        if best not in filtered_streams:
                            filtered_streams.append(best)
            else:
                filtered_streams = streams

            return filtered_streams

        for stream_type in list(StreamType):
            streams = client_manifest.list_streams(stream_type)

            media[stream_type] = filter_streams(streams, stream_type)
            chunks[stream_type] = client_manifest.get_chunks_count(stream_type)

        return media, chunks

    def __download_stream(self, episode_id, episode_path, stream, stream_type, chunks):
        _, server_manifest = self.__get_episode_manifests(episode_id)

        if stream_type == StreamType.Video:
            stream = server_manifest.get_video_stream(stream.bitrate)
        else:
            stream = server_manifest.get_named_stream(
                stream.name, stream_type, stream.bitrate
            )

        if stream is None:
            self.__progress_stream.console.log(
                f"[red]Error:[/red] Stream {stream} not found in server manifest for episode {episode_id}."
            )
            return

        filename = stream.attributes.get("src")
        media_url = self.__video_list.get_media_url(episode_id, filename)

        self.__progress_stream.console.log(
            f"[{episode_id}] Downloading {stream_type.value} media file: {filename}"
        )
        self.__download_media(media_url, chunks, episode_path / filename)

    def __download_media(self, mediaUrl: str, chunks: int, outputPath: Path):
        progress_media = self.__progress_media.add_task(
            f"Downloading {outputPath.name}..."
        )

        with requests.head(mediaUrl) as r:
            r.raise_for_status()
            contentLength = int(r.headers["Content-Length"])

        self.__progress_media.update(progress_media, total=contentLength)

        chunkSize = max(
            ceil(contentLength / chunks), CHUNK_SIZE
        )  # Segment-ish size or 1MB

        if outputPath.exists():
            # Resume from where we left
            currentRange = outputPath.stat().st_size
        else:
            currentRange = 0

        self.__progress_media.update(progress_media, completed=currentRange)

        with open(outputPath, "ab") as f:
            while currentRange < contentLength:
                endRange = min(currentRange + chunkSize, contentLength)

                headers = self.__session.headers.copy()  # type: ignore
                headers["X-MS-Range"] = f"bytes={currentRange}-{endRange}"

                try:
                    with self.__session.get(
                        mediaUrl, headers=headers, stream=True
                    ) as r:
                        r.raise_for_status()

                        dlBytes = 0

                        for chunk in r.iter_content(chunk_size=1024):
                            f.write(chunk)
                            currentRange += len(chunk)
                            dlBytes += len(chunk)

                        self.__progress_media.update(progress_media, advance=dlBytes)
                except ChunkedEncodingError:
                    self.__progress_media.console.log(
                        f"[red]Error:[/red] Chunked encoding error while downloading {outputPath.name}. Retrying..."
                    )
                    time.sleep(1)
                    continue

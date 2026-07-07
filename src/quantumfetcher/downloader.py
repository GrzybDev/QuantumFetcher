from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import time
import threading
from math import ceil
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter, Retry
from requests.exceptions import ChunkedEncodingError, RequestException
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
from quantumfetcher.subtitles import extract_subtitles
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

    __progress_fragment = Progress(
        SpinnerColumn(finished_text="\u2713"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    )

    __progress_group = Group(
        __progress_overall, __progress_stream, __progress_media, __progress_fragment
    )
    __request_timeout = 30

    def __init__(self, fragment_workers: int = 8):
        self.__fragment_workers = max(1, min(fragment_workers, 16))
        self.__thread_local = threading.local()
        self.__session = self.__create_session()

    def __create_session(self):
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})

        retries = Retry(total=10, backoff_factor=3)

        adapter = HTTPAdapter(max_retries=retries)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def __get_fragment_session(self):
        session = getattr(self.__thread_local, "session", None)
        if session is None:
            session = self.__create_session()
            self.__thread_local.session = session
        return session

    def __fetch_file(self, url: str) -> str:
        headers = self.__session.headers.copy()  # type: ignore
        headers["Accept-Encoding"] = "deflate"

        r = self.__session.get(url, headers=headers, timeout=self.__request_timeout)
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
        extract_subtitles: bool,
    ):
        self.__video_list = video_list
        self.__manifests = manifests
        self.__download_path = episodes_path
        self.__streams_video = video_streams
        self.__streams_audio = audio_streams
        self.__streams_text = text_streams
        self.__extract_subtitles = extract_subtitles
        self.__fragment_workers = max(1, min(self.__fragment_workers, 16))

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
    ) -> tuple[ClientManifest, ServerManifest | None]:
        episode_manifests = self.__manifests[episode_id]
        client_manifest = episode_manifests[ManifestType.Client]

        if not isinstance(client_manifest, ClientManifest):
            raise TypeError(
                f"Expected ClientManifest for episode {episode_id}, got {type(client_manifest)}"
            )

        server_manifest = episode_manifests.get(ManifestType.Server)
        if server_manifest is None:
            return client_manifest, None

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

        if server_manifest is None:
            self.__download_episode_fragments(
                episode_id,
                episode_path,
                streams_to_download,
                client_manifest,
            )
            return

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

        client_manifest.save(episode_path / client_manifest_path, streams_to_download)
        server_manifest.save(
            episode_path / self.__video_list.get_server_manifest_name(episode_id),
            streams_to_download,
        )

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

        if server_manifest is None:
            return

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

        if stream_type == StreamType.Text and self.__extract_subtitles:
            self.__progress_stream.console.log(
                f"[{episode_id}] Extracting subtitles from {filename}..."
            )
            match = re.match(r"J(\d).*", episode_id)
            episode_id_str = "-1"

            if match:
                episode_id_str = match.group(1)

            extract_subtitles(
                episode_path / filename,
                episode_num=int(episode_id_str),
                track_name=stream.parameters.get("trackName", "unknown"),
            )

            self.__progress_stream.console.log(
                f"[{episode_id}] Finished extracting subtitles from {filename}."
            )

    def __download_media(self, mediaUrl: str, chunks: int, outputPath: Path):
        progress_media = self.__progress_media.add_task(
            f"Downloading {outputPath.name}..."
        )

        with self.__session.head(mediaUrl, timeout=self.__request_timeout) as r:
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
                        mediaUrl,
                        headers=headers,
                        stream=True,
                        timeout=self.__request_timeout,
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

    def __download_episode_fragments(
        self,
        episode_id: str,
        episode_path: Path,
        streams_to_download: list,
        client_manifest: ClientManifest,
    ):
        client_manifest_path = episode_path / "manifest"
        client_manifest.save(client_manifest_path, streams_to_download)

        fragment_jobs = []
        stream_fragment_counts = {}

        for stream_index, stream in enumerate(streams_to_download):
            fragment_paths = client_manifest.get_fragment_paths(stream)
            stream_fragment_counts[stream_index] = len(fragment_paths)

            for fragment_path in fragment_paths:
                media_url = self.__video_list.get_fragment_url(
                    episode_id, fragment_path.as_posix()
                )
                fragment_jobs.append(
                    (stream_index, media_url, episode_path / fragment_path)
                )

        task_id = self.__progress_stream.add_task(
            f"Downloading fragment files for {episode_id}...",
            total=len(streams_to_download),
        )

        fragment_task = self.__progress_fragment.add_task(
            f"Downloading fragments for {episode_id}...",
            total=len(fragment_jobs),
        )

        try:
            with ThreadPoolExecutor(max_workers=self.__fragment_workers) as executor:
                futures = {
                    executor.submit(self.__download_fragment, media_url, output_path): stream_index
                    for stream_index, media_url, output_path in fragment_jobs
                }

                stream_remaining = dict(stream_fragment_counts)

                for future in as_completed(futures):
                    stream_index = futures[future]
                    future.result()

                    self.__progress_fragment.update(fragment_task, advance=1)

                    stream_remaining[stream_index] -= 1
                    if stream_remaining[stream_index] == 0:
                        self.__progress_stream.update(task_id, advance=1)
        finally:
            self.__progress_fragment.remove_task(fragment_task)
            self.__progress_stream.remove_task(task_id)

    def __download_fragment(self, media_url: str, output_path: Path):
        if output_path.exists() and output_path.stat().st_size > 0:
            return

        output_path.parent.mkdir(exist_ok=True, parents=True)
        temp_path = output_path.with_name(output_path.name + ".part")

        if temp_path.exists():
            temp_path.unlink()

        progress_media = self.__progress_fragment.add_task(
            f"Downloading {output_path.name}..."
        )

        try:
            session = self.__get_fragment_session()
            with session.get(
                media_url,
                stream=True,
                timeout=self.__request_timeout,
            ) as r:
                r.raise_for_status()
                content_length = int(r.headers.get("Content-Length", "0"))
                if content_length:
                    self.__progress_fragment.update(progress_media, total=content_length)

                with open(temp_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 64):
                        if not chunk:
                            continue

                        f.write(chunk)
                        self.__progress_fragment.update(progress_media, advance=len(chunk))

            temp_path.replace(output_path)
        except RequestException:
            if temp_path.exists():
                temp_path.unlink()
            raise
        finally:
            self.__progress_fragment.remove_task(progress_media)

import re

import typer
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

from quantumfetcher.downloader import download_media
from quantumfetcher.enumerators.StreamType import StreamType
from quantumfetcher.subtitles import extract_subtitles


class DownloadFlow:

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

    __progress_subtitle = Progress(
        SpinnerColumn(finished_text="\u2713"),
        TextColumn("[progress.description]{task.description}"),
    )

    __progress_group = Group(
        __progress_overall, __progress_stream, __progress_media, __progress_subtitle
    )

    def __init__(self, videoList, manifests, output_path, extract_subtitles) -> None:
        self.__videoList = videoList
        self.__manifests = manifests
        self.__output_path = output_path
        self.__extract_subtitles = extract_subtitles

        output_path.mkdir(exist_ok=True)

    def download(self, fetch_episodes, fetch_qualities):
        with Live(self.__progress_group, refresh_per_second=10):
            progress_overall = self.__progress_overall.add_task(
                "Downloading episodes...", total=len(fetch_episodes)
            )

            for episode in fetch_episodes:
                self.__progress_overall.update(
                    progress_overall, description=f"Downloading {episode}..."
                )

                self.__download_episode(episode, fetch_qualities)

                self.__progress_overall.update(progress_overall, advance=1)

            self.__progress_overall.update(
                progress_overall, completed=True, visible=False
            )

    def __get_streams_to_fetch(self, episode_id, qualities):
        # Get only the streams that match the quality
        server_manifest, client_manifest = self.__manifests[episode_id]
        output = {StreamType.Video: [], StreamType.Audio: [], StreamType.Text: []}

        for stream_type in qualities:
            for ql in qualities[stream_type]:
                match stream_type:
                    case StreamType.Video:
                        stream = server_manifest.get_video_stream(ql.bitrate)
                        chunks = client_manifest.get_chunks_count(StreamType.Video)

                        if stream:
                            output[StreamType.Video].append((stream, chunks))
                        else:
                            typer.echo(
                                f"Cannot find Video stream with requested quality for episode {episode_id}, skipping...",
                                err=True,
                            )
                    case StreamType.Audio | StreamType.Text:
                        stream = server_manifest.get_named_stream(
                            ql.name if episode_id != "J1 - 4K Test" else "eng",
                            stream_type,
                            ql.bitrate,
                        )
                        chunks = client_manifest.get_chunks_count(stream_type)

                        if stream:
                            output[stream_type].append((stream, chunks))
                        else:
                            typer.echo(
                                f"Cannot find {stream_type.name} stream ({ql.name}) with requested quality for episode {episode_id}, skipping...",
                                err=True,
                            )
        return output

    def __download_episode(self, episode_id, qualities):
        episode_path = self.__output_path / episode_id
        episode_path.mkdir(exist_ok=True)

        media_to_download = self.__get_streams_to_fetch(episode_id, qualities)

        total_streams = sum(
            len(media_to_download[stream_type]) for stream_type in media_to_download
        )

        progress_stream = self.__progress_stream.add_task(
            "Downloading episode media...", total=total_streams
        )

        for stream_type in media_to_download:
            self.__progress_stream.update(
                progress_stream,
                description=f"Downloading {stream_type.name} Streams...",
            )

            self.__download_streams(
                episode_id,
                episode_path,
                media_to_download[stream_type],
                progress_stream,
                stream_type == StreamType.Text and self.__extract_subtitles,
            )

            self.__progress_stream.advance(progress_stream)

        self.__progress_stream.update(progress_stream, completed=True, visible=False)

    def __download_streams(self, episode_id, episode_path, streams, progress, extract):
        for stream, chunks in streams:
            filename = stream.attributes.get("src")
            media_url = self.__videoList.get_media_url(episode_id, filename)

            download_media(
                media_url, chunks, episode_path / filename, self.__progress_media
            )

            if extract:
                subtitle_task = self.__progress_subtitle.add_task(
                    "Extracting captions...", total=1
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

                self.__progress_subtitle.update(
                    subtitle_task, advance=1, completed=True, visible=False
                )

            self.__progress_stream.update(progress, advance=1)

        for task in self.__progress_media.tasks:
            self.__progress_media.update(task.id, completed=True, visible=False)

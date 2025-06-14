import re

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
from quantumfetcher.enumerators.stream_type import StreamType
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

    __progress_processing = Progress(
        SpinnerColumn(finished_text="\u2713"),
        TextColumn("[progress.description]{task.description}"),
    )

    __progress_group = Group(
        __progress_overall, __progress_stream, __progress_media, __progress_processing
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
                            if (stream, chunks) in output[stream_type]:
                                continue

                            output[StreamType.Video].append((stream, chunks))
                        else:
                            if episode_id == "J1 - 4K Test":
                                continue

                            self.__progress_stream.console.print(
                                f"Cannot find Video stream with requested quality for episode {episode_id}, skipping...",
                            )
                    case StreamType.Audio | StreamType.Text:
                        trackName = ql.name

                        if (
                            stream_type == StreamType.Audio
                            and trackName == "enus"
                            and episode_id == "J1 - 4K Test"
                        ):
                            trackName = "eng"
                        elif (
                            stream_type == StreamType.Audio
                            and trackName == "eng"
                            and episode_id != "J1 - 4K Test"
                        ):
                            continue

                        stream = server_manifest.get_named_stream(
                            trackName,
                            stream_type,
                            ql.bitrate,
                        )
                        chunks = client_manifest.get_chunks_count(stream_type)

                        if stream:
                            if (stream, chunks) in output[stream_type]:
                                continue

                            output[stream_type].append((stream, chunks))
                        else:
                            if episode_id == "J1 - 4K Test":
                                continue

                            self.__progress_stream.console.print(
                                f"Cannot find {stream_type.name} stream ({trackName}) with requested quality for episode {episode_id}, skipping...",
                            )
        return output

    def __download_episode(self, episode_id, qualities):
        episode_path = self.__output_path / episode_id
        episode_path.mkdir(exist_ok=True)

        media_to_download = self.__get_streams_to_fetch(episode_id, qualities)
        media_downloaded = {
            StreamType.Video: [],
            StreamType.Audio: [],
            StreamType.Text: [],
        }

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

            dl_streams = self.__download_streams(
                episode_id,
                episode_path,
                media_to_download[stream_type],
                progress_stream,
                stream_type == StreamType.Text and self.__extract_subtitles,
            )
            media_downloaded[stream_type].extend(dl_streams)

        manifests_progress = self.__progress_processing.add_task(
            f"Saving episode server manifest...", total=2
        )

        server_manifest, client_manifest = self.__manifests[episode_id]

        server_manifest.remove_not_downloaded_streams(media_downloaded)

        server_manifest.save(
            episode_path / self.__videoList.get_server_manifest_filename(episode_id)
        )

        clientManifestFilename = server_manifest.get_client_manifest_relative_path()

        self.__progress_processing.update(
            manifests_progress,
            advance=1,
            description="Saving episode client manifest...",
        )

        client_manifest.remove_not_downloaded_streams(media_downloaded)

        client_manifest.save(episode_path / clientManifestFilename)

        self.__progress_processing.update(
            manifests_progress, advance=1, completed=True, visible=False
        )

        self.__progress_stream.update(progress_stream, completed=True, visible=False)

    def __download_streams(self, episode_id, episode_path, streams, progress, extract):
        finished_streams = []

        for stream, chunks in streams:
            filename = stream.attributes.get("src")
            media_url = self.__videoList.get_media_url(episode_id, filename)

            download_media(
                media_url, chunks, episode_path / filename, self.__progress_media
            )

            finished_streams.append(stream)

            if extract:
                subtitle_task = self.__progress_processing.add_task(
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

                self.__progress_processing.update(
                    subtitle_task, advance=1, completed=True, visible=False
                )

            self.__progress_stream.update(progress, advance=1)

        for task in self.__progress_media.tasks:
            self.__progress_media.update(task.id, completed=True, visible=False)

        return finished_streams

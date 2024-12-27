from pathlib import Path
from urllib.parse import unquote, urlparse, urlunparse

import requests
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

from quantumfetcher.helpers import update_manifests
from quantumfetcher.rmdj import RMDJ
from quantumfetcher.smooth import Smooth

EPISODES_PATH = "videos/episodes"


class Downloader:

    progress_overall = Progress(
        SpinnerColumn(finished_text="\u2713"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    )

    progress_manifest = Progress(
        SpinnerColumn(finished_text="\u2713"),
        TextColumn("[progress.description]{task.description}"),
    )

    progress_stream = Progress(
        SpinnerColumn(finished_text="\u2713"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
    )

    progress_download = Progress(
        SpinnerColumn(finished_text="\u2713"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    )

    progress_group = Group(
        progress_overall,
        Group(progress_manifest, progress_stream, progress_download),
    )

    episodes_to_fetch: list[str]
    fetch_languages_audio: list[str] | None
    fetch_languages_subtitle: list[str] | None
    fetch_all: bool
    max_video_bitrate: int
    max_audio_bitrate: int
    extract_subtitles: bool

    __overall_progress: int = 0

    __path: str
    __rmdj: RMDJ

    def __init__(
        self,
        path: str,
        rmdj: RMDJ,
        episodes_to_fetch: list[str],
        max_video_bitrate: int,
        max_audio_bitrate: int,
        fetch_languages_audio: list[str],
        fetch_languages_subtitle: list[str],
        fetch_all: bool,
        extract_subtitles: bool,
    ):
        self.__path = path
        self.__rmdj = rmdj
        self.episodes_to_fetch = episodes_to_fetch
        self.max_video_bitrate = max_video_bitrate
        self.max_audio_bitrate = max_audio_bitrate
        self.fetch_languages_audio = fetch_languages_audio
        self.fetch_languages_subtitle = fetch_languages_subtitle
        self.fetch_all = fetch_all
        self.extract_subtitles = extract_subtitles

    def download_flow(self):
        with Live(self.progress_group):
            self.__overall_progress = self.progress_overall.add_task(
                "Downloading episodes...", total=len(self.episodes_to_fetch)
            )

            for episode in self.episodes_to_fetch:
                self.progress_overall.update(
                    self.__overall_progress,
                    advance=0,
                    description=f"Downloading {episode}",
                )
                self.__download_episode(episode)
                self.progress_overall.update(self.__overall_progress, advance=1)

    def __download_episode(self, episode: str):
        episode_url = self.__rmdj.get_episode_url(episode)

        if not episode_url:
            self.progress_overall.log(
                f"Episode {episode} not found in video list. Skipping."
            )
            return

        episode_path = self.__path / EPISODES_PATH / episode
        episode_path.mkdir(exist_ok=True)

        __cleaned_url = urlparse(episode_url)._replace(query="")
        ism_url = urlunparse(__cleaned_url).replace("/manifest", "")
        __ism_filename = unquote(ism_url.rsplit("/", 1)[1])
        base_url = ism_url.rsplit("/", 1)[0]

        ism = self.__download_manifest(
            "server", ism_url, episode_path / __ism_filename, base_url=base_url
        )

        self.__download_manifest(
            "client",
            episode_url,
            episode_path / ism.get_client_manifest_relative_path(),
        )

        self.__download_video_streams(ism, episode_path)
        self.__download_audio_streams(ism, episode_path)
        self.__download_text_streams(ism, episode_path)

        update_manifests(episode_path)

        self.__clean_up_progress()

    def __download_manifest(
        self, manifest_type: str, manifest_url: str, path: Path, base_url: str = None
    ):
        manifest_task = self.progress_manifest.add_task(
            f"Downloading {manifest_type} manifest...", total=1
        )

        final_bytes = None

        if not path.exists():
            path.parent.mkdir(exist_ok=True)

            with open(path, "wb") as f:
                response = requests.get(manifest_url)
                response.raise_for_status()

                f.write(response.content)

            final_bytes = response.content
        else:
            with open(path, "rb") as f:
                final_bytes = f.read()

        ism = None

        if manifest_type == "server":
            ism = Smooth(final_bytes, base_url)

        self.progress_manifest.update(manifest_task, advance=1)

        return ism

    def __download_video_streams(self, ism: Smooth, episode_path: Path):
        video_bitrates = ism.get_available_video_bitrates()

        if self.fetch_all:
            progress_stream_task = self.progress_stream.add_task(
                "Downloading video streams...",
                total=len(video_bitrates),
            )

            for bitrate in video_bitrates:
                ism.download_video(bitrate, episode_path, self.progress_download)
                self.progress_stream.update(progress_stream_task, advance=1)
        else:
            selected_video_bitrate = ism.get_highest_video_bitrate(
                self.max_video_bitrate
            )

            ism.download_video(
                selected_video_bitrate, episode_path, self.progress_download
            )

    def __download_audio_streams(self, ism: Smooth, episode_path: Path):
        audio_languages = ism.get_available_audio_bitrates()

        if self.fetch_languages_audio:
            audio_languages = {
                lang: [
                    bitrate
                    for bitrate in bitrates
                    if lang in self.fetch_languages_audio
                ]
                for lang, bitrates in audio_languages.items()
            }

            # Remove languages with no bitrates
            audio_languages = {
                lang: bitrates for lang, bitrates in audio_languages.items() if bitrates
            }

        if self.max_audio_bitrate:
            audio_languages = {
                lang: [
                    bitrate for bitrate in bitrates if bitrate <= self.max_audio_bitrate
                ]
                for lang, bitrates in audio_languages.items()
            }

        progress_stream_task = None

        if len(audio_languages.keys()) > 1:
            progress_stream_task = self.progress_stream.add_task(
                f"Downloading localized audio streams...",
                total=len(audio_languages),
            )

        if self.fetch_all:
            for lang in audio_languages:
                if progress_stream_task != None:
                    self.progress_stream.update(
                        progress_stream_task,
                        advance=0,
                        description=f"Downloading {lang} audio streams...",
                    )

                progress_lang = self.progress_stream.add_task(
                    f"Downloading audio streams...",
                    total=len(audio_languages[lang]),
                )

                for bitrate in audio_languages[lang]:
                    ism.download_audio(
                        lang, bitrate, episode_path, self.progress_download
                    )
                    self.progress_stream.update(progress_lang, advance=1)

                if progress_stream_task != None:
                    self.progress_stream.update(progress_stream_task, advance=1)
        else:
            for lang in audio_languages:
                if progress_stream_task != None:
                    self.progress_stream.update(
                        progress_stream_task,
                        advance=0,
                        description=f"Downloading {lang} audio stream...",
                    )

                select_audio_bitrate = ism.get_highest_audio_bitrate(
                    lang, self.max_audio_bitrate
                )

                ism.download_audio(
                    lang, select_audio_bitrate, episode_path, self.progress_download
                )

                if progress_stream_task != None:
                    self.progress_stream.update(progress_stream_task, advance=1)

    def __download_text_streams(self, ism: Smooth, episode_path: Path):
        text_languages = ism.get_available_text_languages()

        if self.fetch_languages_subtitle:
            text_languages = [
                lang for lang in text_languages if lang in self.fetch_languages_subtitle
            ]

        if not text_languages:
            return

        progress_lang = None

        if len(text_languages) > 1:
            progress_lang = self.progress_stream.add_task(
                f"Downloading text streams...",
                total=len(text_languages),
            )

        for lang in text_languages:
            ism.download_text(
                lang, episode_path, self.extract_subtitles, self.progress_download
            )

            if progress_lang != None:
                self.progress_stream.update(progress_lang, advance=1)

    def __clean_up_progress(self):
        # Hide all tasks

        for task in self.progress_download.tasks:
            self.progress_download.update(task.id, visible=False)

        for task in self.progress_stream.tasks:
            self.progress_stream.update(task.id, visible=False)

        for task in self.progress_manifest.tasks:
            self.progress_manifest.update(task.id, visible=False)

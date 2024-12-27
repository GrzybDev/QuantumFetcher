from pathlib import Path

import typer

from quantumfetcher.downloader import Downloader
from quantumfetcher.rmdj import RMDJ

app = typer.Typer()

GAME_VIDEOLIST = "data/videoList.rmdj"
ORIGINAL_VIDEOLIST = "data/videoList_original.rmdj"
EPISODES_PATH = "videos/episodes"


@app.command()
def download(
    path: Path = typer.Argument(help="Path to the game folder"),
    fetch_episodes: str = typer.Option(
        None,
        help="Comma-separated list of episodes to fetch. If not provided, all episodes will be fetched.",
    ),
    max_video_bitrate: int = typer.Option(
        None, help="If set, maximum video bitrate to fetch"
    ),
    max_audio_bitrate: int = typer.Option(
        None, help="If set, maximum audio bitrate to fetch"
    ),
    audio_languages: str = typer.Option(
        "eng", help="Comma-separated list of audio languages to fetch"
    ),
    subtitle_languages: str = typer.Option(
        "eng", help="Comma-separated list of subtitle languages to fetch"
    ),
    fetch_all_qualities: bool = typer.Option(
        False, help="If set, fetch all available video and audio qualities"
    ),
    extract_subtitles: bool = typer.Option(
        False, help="Extract subtitles to .json after fetching"
    ),
):
    if audio_languages == "all":
        audio_languages = None
    else:
        audio_languages = audio_languages.split(",")

    if subtitle_languages == "all":
        subtitle_languages = None
    else:
        subtitle_languages = subtitle_languages.split(",")

    videoList_path = path / GAME_VIDEOLIST

    if (path / ORIGINAL_VIDEOLIST).exists():
        videoList_path = path / ORIGINAL_VIDEOLIST

    if not videoList_path.exists():
        raise typer.BadParameter(
            f"File {videoList_path} does not exist! Cannot continue."
        )

    rmdj = RMDJ(videoList_path)
    episodes_to_fetch = (
        fetch_episodes.split(",") if fetch_episodes else rmdj.get_episodes()
    )

    (path / EPISODES_PATH).mkdir(exist_ok=True)

    downloader = Downloader(
        path,
        rmdj,
        episodes_to_fetch,
        max_video_bitrate,
        max_audio_bitrate,
        audio_languages,
        subtitle_languages,
        fetch_all_qualities,
        extract_subtitles,
    )

    downloader.download_flow()


if __name__ == "__main__":
    app()

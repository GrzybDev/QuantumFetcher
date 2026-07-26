from pathlib import Path
from typing import Annotated

import typer

from quantumfetcher.flow import Flow
from quantumfetcher.helpers import get_game_dir, get_videolist_path
from quantumfetcher.video_list import VideoList, videolist_app
from quantumfetcher.prompt import Prompt

app = typer.Typer(
    help="Tool for fetching Quantum Break live action episodes for offline in-game playback"
)
app.add_typer(
    videolist_app, name="videolist", help="Manage the videoList.rmdj manifest file"
)


@app.command("download")
def download(
    path: Annotated[
        Path | None,
        typer.Argument(
            help="Path to root game folder", exists=True, dir_okay=True, readable=True
        ),
    ] = None,
    videolist_path: Annotated[
        Path | None,
        typer.Option(
            help="Path to videoList.rmdj file (defaults to data/videoList.rmdj inside game folder)",
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
    episodes: Annotated[
        str | None,
        typer.Option(
            help="Comma-separated list of episode IDs to fetch. If not provided, all episodes will be fetched"
        ),
    ] = None,
    episodes_path: Annotated[
        Path | None,
        typer.Option(
            help="Path to where episodes will be saved (defaults to videos/episodes inside game folder)",
            dir_okay=True,
            writable=True,
            readable=True,
        ),
    ] = None,
    video_resolutions: Annotated[
        str | None,
        typer.Option(
            help="Comma-seperated list of video resolutions to download (e.g., 1080p, 720p)",
        ),
    ] = None,
    video_bitrates: Annotated[
        str | None,
        typer.Option(
            help="Comma-seperated list of video bitrates to download",
        ),
    ] = None,
    audio_languages: Annotated[
        str | None,
        typer.Option(
            help="Comma-seperated list of audio languages to download",
        ),
    ] = None,
    audio_bitrates: Annotated[
        str | None,
        typer.Option(
            help="Comma-seperated list of audio bitrates to download",
        ),
    ] = None,
    text_languages: Annotated[
        str | None,
        typer.Option(
            help="Comma-seperated list of text languages to download",
        ),
    ] = None,
    text_bitrates: Annotated[
        str | None,
        typer.Option(
            help="Comma-seperated list of text bitrates to download",
        ),
    ] = None,
    show_formats: Annotated[
        bool,
        typer.Option(
            help="Show available formats for video/audio/text streams without downloading",
            is_flag=True,
        ),
    ] = False,
    extract_subtitles: Annotated[
        bool, typer.Option(help="Extract subtitles", is_flag=True)
    ] = False,
    append_episode_title: Annotated[
        bool, typer.Option(help="Append episode title to extracted subtitles", is_flag=True)
    ] = False,
):
    """Download episodes for local playback"""
    interactive = False

    if not path and not videolist_path:
        interactive = True
        path = Prompt.get_game_path()

    game_path = get_game_dir(path) if not videolist_path else Path()
    vl_path = get_videolist_path(game_path, videolist_path)

    if not episodes_path:
        episodes_path = game_path / "videos" / "episodes"

    video_list = VideoList(vl_path, is_game_dir=bool(not videolist_path))

    if not episodes:
        interactive = True
        episodes_list = Prompt.select_episodes(video_list)
        episodes = ",".join(episodes_list)

    if (
        (not video_resolutions and not video_bitrates)
        or (not audio_languages and not audio_bitrates)
        or (not text_languages and not text_bitrates)
    ):
        interactive = True

    Flow(
        interactive=interactive,
        video_list=video_list,
        episodes=episodes.split(",") if episodes else None,
        episodes_path=episodes_path,
        video_resolutions=video_resolutions.split(",") if video_resolutions else None,
        video_bitrates=video_bitrates.split(",") if video_bitrates else None,
        audio_langs=audio_languages.split(",") if audio_languages else None,
        audio_bitrates=audio_bitrates.split(",") if audio_bitrates else None,
        text_langs=text_languages.split(",") if text_languages else None,
        text_bitrates=text_bitrates.split(",") if text_bitrates else None,
        show_formats=show_formats,
        extract_subtitles=extract_subtitles,
        append_episode_title=append_episode_title,
    )

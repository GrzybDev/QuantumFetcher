from pathlib import Path
from typing import Annotated

import typer

from quantumfetcher.flow import Flow
from quantumfetcher.prompt import Prompt
from quantumfetcher.video_list import VideoList

app = typer.Typer()


@app.command(
    help="Tool for fetching Quantum Break live action episodes for offline in-game playback"
)
def main(
    path: Annotated[
        Path | None,
        typer.Argument(
            help="Path to root game folder", exists=True, dir_okay=True, readable=True
        ),
    ] = None,
    videolist_path: Annotated[
        Path,
        typer.Option(
            help="Path to videoList.rmdj file",
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ] = Path("data/videoList.rmdj"),
    dump_videolist_path: Annotated[
        Path | None,
        typer.Option(
            help="Dump videoList.rmdj to specified file or stdout if '-' is provided",
            is_flag=True,
        ),
    ] = None,
    patch_videolist: Annotated[
        bool,
        typer.Option(
            help="Patch videoList.rmdj to point to custom QuantumStreamer compatible server",
            is_flag=True,
        ),
    ] = False,
    patch_videolist_server: Annotated[
        str,
        typer.Option(
            help="Custom streaming server host",
        ),
    ] = "127.0.0.1:10000",
    build_videolist_path: Annotated[
        Path | None,
        typer.Option(
            help="Build videoList.rmdj from specified JSON file",
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
    interactive: Annotated[
        bool,
        typer.Option(
            help="Run in interactive mode",
            is_flag=True,
        ),
    ] = False,
    episodes: Annotated[
        str | None,
        typer.Option(
            help="Comma-separated list of episode IDs to fetch. If not provided, all episodes will be fetched"
        ),
    ] = None,
    video_resolutions: Annotated[
        str | None,
        typer.Option(
            help="Comma-seperated list of video resolutions to download (e.g., 720p, 1080p, 2160p)",
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
            help="Show available formats for video/audio/text streams",
            is_flag=True,
        ),
    ] = False,
):
    if (
        path is None
        and not dump_videolist_path
        and not patch_videolist
        and not build_videolist_path
    ):
        # Ask user for path to root game folder
        interactive = True
        path = Prompt.get_game_path()

    is_game_dir = False

    if path and videolist_path == Path("data/videoList.rmdj"):
        # If no videoList.rmdj is provided, use the default one
        videolist_path = path / "data" / "videoList.rmdj"
        is_game_dir = True

    if build_videolist_path:
        return VideoList.build(build_videolist_path, videolist_path)

    video_list = VideoList(videolist_path, is_game_dir)

    if dump_videolist_path:
        if dump_videolist_path == Path("-"):
            # If dump_videolist_path is "-", print to stdout
            dump_videolist_path = None

        return video_list.dump(dump_videolist_path)

    if patch_videolist:
        return video_list.patch(patch_videolist_server)

    Flow(
        interactive=interactive,
        video_list=video_list,
        episodes=episodes.split(",") if episodes else None,
        video_resolutions=video_resolutions.split(",") if video_resolutions else None,
        video_bitrates=video_bitrates.split(",") if video_bitrates else None,
        audio_langs=audio_languages.split(",") if audio_languages else None,
        audio_bitrates=audio_bitrates.split(",") if audio_bitrates else None,
        text_langs=text_languages.split(",") if text_languages else None,
        text_bitrates=text_bitrates.split(",") if text_bitrates else None,
        show_formats=show_formats,
    )


if __name__ == "__main__":
    app()

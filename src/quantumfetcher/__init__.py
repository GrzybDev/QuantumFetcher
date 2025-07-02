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
    )


if __name__ == "__main__":
    app()

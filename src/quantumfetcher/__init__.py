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
    dump_videolist: Annotated[
        bool,
        typer.Option(
            help="Dump videoList.rmdj to console",
            is_flag=True,
        ),
    ] = False,
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
):
    if path is None:
        # Ask user for path to root game folder
        path = Prompt.get_game_path()

    if path and videolist_path == Path("data/videoList.rmdj"):
        # If no videoList.rmdj is provided, use the default one
        videolist_path = path / "data" / "videoList.rmdj"

    video_list = VideoList(videolist_path)

    if dump_videolist:
        return video_list.dump()

    if patch_videolist:
        return video_list.patch(patch_videolist_server)

    Flow(video_list)


if __name__ == "__main__":
    app()

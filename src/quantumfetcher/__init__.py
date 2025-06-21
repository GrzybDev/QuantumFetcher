from pathlib import Path
from typing import Annotated

import typer

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
):
    if path is None:
        # Ask user for path to root game folder
        path = typer.prompt("Enter path to root game folder", type=Path)

    if path and videolist_path == Path("data/videoList.rmdj"):
        # If no videoList.rmdj is provided, use the default one
        videolist_path = path / "data" / "videoList.rmdj"

    video_list = VideoList(videolist_path)

    if dump_videolist:
        return video_list.dump()


if __name__ == "__main__":
    app()

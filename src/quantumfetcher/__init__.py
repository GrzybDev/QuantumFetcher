from pathlib import Path
from typing import Annotated

import typer

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
):
    if path is None:
        # Ask user for path to root game folder
        path = typer.prompt("Enter path to root game folder", type=Path)


if __name__ == "__main__":
    app()

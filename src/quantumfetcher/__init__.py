from pathlib import Path
from typing import Annotated, Optional

from typer import Argument, Option, Typer

from quantumfetcher.interactive import InteractiveMain

app = Typer()


@app.command()
def main(
    path: Annotated[Path, Argument(exists=True, dir_okay=True, readable=True)],
    videolist_path: Annotated[
        Optional[Path],
        Option(
            help=(
                "Relative path to videoList.rmdj file "
                "(will also additionally check if filename_original.rmdj exist)"
            )
        ),
    ] = Path("data/videoList.rmdj"),
):
    InteractiveMain(path, videolist_path)  # type: ignore


if __name__ == "__main__":
    app()

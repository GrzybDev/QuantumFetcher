from pathlib import Path
from typing import Annotated

from typer import Argument, Option, Typer

from quantumfetcher.helpers import print_available_formats
from quantumfetcher.interactive import InteractiveMain
from quantumfetcher.noninteractive import NonInteractiveMain

app = Typer()


@app.command()
def main(
    path: Annotated[Path, Argument(exists=True, dir_okay=True, readable=True)],
    videolist_path: Annotated[
        Path | None,
        Option(
            help=(
                "Relative path to videoList.rmdj file "
                "(will also additionally check if filename_original.rmdj exist)"
            )
        ),
    ] = Path("data/videoList.rmdj"),
    episodes_path: Annotated[
        Path | None,
        Option(help=("Relative output path to where episode data will be downloaded")),
    ] = Path("videos/episodes"),
    # Non-interactive options
    episodes: Annotated[
        str | None, Option(help="Comma-separated list of episode IDs to download")
    ] = None,
    video_bitrates: Annotated[
        str | None, Option(help="Comma-seperated list of video bitrates to download")
    ] = None,
    audio_langs: Annotated[
        str | None, Option(help="Comma-seperated list of audio languages to download")
    ] = None,
    audio_bitrates: Annotated[
        str | None, Option(help="Comma-seperated list of audio bitrates to download")
    ] = None,
    text_langs: Annotated[
        str | None, Option(help="Comma-seperated list of text languages to download")
    ] = None,
    text_bitrates: Annotated[
        str | None, Option(help="Comma-seperated list of text bitrates to download")
    ] = None,
    extract_subtitles: Annotated[
        bool, Option(help="Extract subtitles to JSON file", is_flag=True)
    ] = False,
    show_formats: Annotated[
        bool,
        Option(
            help=(
                "Show available formats for video/audio/text streams. "
                "Audio/text also shows language."
            ),
            is_flag=True,
        ),
    ] = False,
):
    """
    Main entrypoint. If --episodes is provided, runs in non-interactive mode.
    Otherwise, runs interactive mode.
    """

    if show_formats:
        return print_available_formats(
            path / (videolist_path or Path("data/videoList.rmdj")), episodes
        )

    if episodes:
        NonInteractiveMain(
            path,
            videolist_path or Path("data/videoList.rmdj"),
            episodes_path or Path("videos/episodes"),
            episodes,
            video_bitrates,
            audio_langs,
            audio_bitrates,
            text_langs,
            text_bitrates,
            extract_subtitles,
        )
    else:
        InteractiveMain(path, videolist_path, episodes_path)  # type: ignore


if __name__ == "__main__":
    app()

from pathlib import Path

import typer


def get_game_dir(path: Path | None) -> Path:
    if path is None:
        path_str = typer.prompt("Enter the path to the root game folder")
        return Path(path_str)
    return path


def get_videolist_path(path: Path, videolist_path: Path | None) -> Path:
    if videolist_path:
        return videolist_path
    return path / "data" / "videoList.rmdj"

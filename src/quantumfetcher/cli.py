import json
import logging
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence, Sized
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from rich.console import Console
from rich.filesize import decimal
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    DownloadColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table

from quantumfetcher import prompts, selection, videolist
from quantumfetcher.download import TrackDownloader
from quantumfetcher.episodes import Episode, EpisodeDownloader, fetch_episodes
from quantumfetcher.errors import FetchError
from quantumfetcher.game import GameFolder
from quantumfetcher.manifest import StreamType, Track
from quantumfetcher.network import DEFAULT_CONNECTIONS, DEFAULT_RETRIES, HttpClient

app = typer.Typer(
    help="Fetch Quantum Break's live action episodes for offline in-game playback.",
    no_args_is_help=True,
)
videolist_app = typer.Typer(
    help="Read and write videoList.rmdj, the game's list of episodes.", no_args_is_help=True
)
app.add_typer(videolist_app, name="videolist")

log = logging.getLogger(__name__)

_console = Console(stderr=True)

GameDir = Annotated[
    Path | None,
    typer.Argument(
        exists=True,
        file_okay=False,
        readable=True,
        show_default=False,
        help="The game folder, holding the data and videos folders. Asked for when left out.",
    ),
]
VideoListPath = Annotated[
    Path | None,
    typer.Option(dir_okay=False, help="videoList.rmdj to use instead of the game folder's."),
]
EpisodeIds = Annotated[
    str | None,
    typer.Option("--episodes", "-e", help="Comma-separated episode IDs, or all."),
]


def _default(kind: StreamType) -> str:
    return ",".join(selection.DEFAULTS[kind])


Retries = Annotated[int, typer.Option(min=0, help="Times to retry a failed request.")]
Workers = Annotated[int, typer.Option(min=1, help="Requests to make at once.")]


@app.callback()
def main(context: typer.Context) -> None:
    logger = logging.getLogger("quantumfetcher")
    handler = RichHandler(console=_console, show_time=False, show_path=False)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    context.call_on_close(lambda: logger.removeHandler(handler))


@app.command(help="Download episodes for QuantumStreamer to play offline.")
def download(
    game_dir: GameDir = None,
    videolist_path: VideoListPath = None,
    episodes_path: Annotated[
        Path | None,
        typer.Option(
            file_okay=False,
            help="Folder to save the episodes in instead of the game folder's videos/episodes.",
        ),
    ] = None,
    episodes: EpisodeIds = None,
    video: Annotated[
        str | None,
        typer.Option(
            show_default=_default(StreamType.VIDEO),
            help="Comma-separated video selectors: best, all, none, a height such as 1080p "
            "or a bitrate.",
        ),
    ] = None,
    audio: Annotated[
        str | None,
        typer.Option(
            show_default=_default(StreamType.AUDIO),
            help="Comma-separated audio selectors: all, none, a stream name such as enus "
            "or a language such as eng.",
        ),
    ] = None,
    text: Annotated[
        str | None,
        typer.Option(
            show_default=_default(StreamType.TEXT),
            help="Comma-separated caption selectors, which pick like audio ones.",
        ),
    ] = None,
    extract_subtitles: Annotated[
        bool | None,
        typer.Option(
            show_default=False,
            help="Save the captions as SubRip files, which QuantumStreamer shows instead.",
        ),
    ] = None,
    append_episode_title: Annotated[
        bool | None,
        typer.Option(show_default=False, help="Add the episode title to the saved subtitles."),
    ] = None,
    retries: Retries = DEFAULT_RETRIES,
    workers: Workers = DEFAULT_CONNECTIONS,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes", "-y", help="Use the defaults instead of asking for what is left out."
        ),
    ] = False,
) -> None:
    interactive = not yes and _interactive()
    given = {StreamType.VIDEO: video, StreamType.AUDIO: audio, StreamType.TEXT: text}
    try:
        if videolist_path is None or episodes_path is None:
            game = _game(game_dir, interactive)
            videolist_path = videolist_path or videolist.unpatched(game.videolist)
            episodes_path = episodes_path or game.episodes
        videos = videolist.load(videolist_path)
        ids = _episode_ids(videos, episodes, interactive)
        with HttpClient(retries, workers) as client:
            loaded = _fetch(client, {episode: videos[episode] for episode in ids}, workers)
            chosen = {
                kind: _selectors(kind, given[kind], loaded, interactive) for kind in StreamType
            }
            plan = [(episode, _tracks(episode, chosen)) for episode in loaded]
            if not any(tracks for _, tracks in plan):
                raise FetchError("The selectors pick no tracks to download")
            with_text = any(track.type is StreamType.TEXT for _, tracks in plan for track in tracks)
            extract = _flag(
                extract_subtitles,
                interactive and with_text,
                "Save the captions as SubRip files that QuantumStreamer shows instead?",
                default=False,
            )
            title = _flag(
                append_episode_title,
                interactive and extract,
                "Add the episode title to the saved subtitles?",
                default=True,
            )
            _log_plan(plan)
            with _transfer_progress() as progress:
                failed = EpisodeDownloader(
                    TrackDownloader(client, workers),
                    episodes_path,
                    partial(_progress_task, progress),
                    extract_subtitles=extract,
                    episode_title=title,
                ).download_all(plan)
    except (FetchError, OSError) as error:
        _fail(error)
    if failed:
        _fail(f"Could not download {len(failed)} of {_count(plan, 'episode')}: {', '.join(failed)}")
    typer.echo(f"Downloaded {_count(plan, 'episode')} to {episodes_path}")


@app.command(help="List the tracks the episodes offer and the selectors that pick them.")
def formats(
    game_dir: GameDir = None,
    videolist_path: VideoListPath = None,
    episodes: EpisodeIds = None,
    retries: Retries = DEFAULT_RETRIES,
    workers: Workers = DEFAULT_CONNECTIONS,
) -> None:
    try:
        videos = videolist.load(_source_videolist(game_dir, videolist_path))
        ids = _episode_ids(videos, episodes, interactive=False)
        with HttpClient(retries, workers) as client:
            loaded = _fetch(client, {episode: videos[episode] for episode in ids}, workers)
    except (FetchError, OSError) as error:
        _fail(error)
    table = Table("Type", "Selector", "Track", "Size per episode", "Episodes")
    for option in selection.options(episode.manifest.tracks for episode in loaded):
        size = "" if option.size is None else f"~{decimal(option.size)}"
        table.add_row(option.type, option.selector, option.description, size, str(option.episodes))
    Console().print(table)


@videolist_app.command(help="Print the video list as JSON, or save it to a file.")
def dump(
    game_dir: GameDir = None,
    videolist_path: VideoListPath = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", dir_okay=False, help="JSON file to save to, or - to print."),
    ] = None,
) -> None:
    try:
        videos = videolist.load(_source_videolist(game_dir, videolist_path))
        text = json.dumps(videos, indent=4)
        if output is None or output == Path("-"):
            typer.echo(text)
        else:
            output.write_text(f"{text}\n", encoding="utf-8")
            typer.echo(f"Saved {_count(videos, 'episode')} to {output}", err=True)
    except (FetchError, OSError) as error:
        _fail(error)


@videolist_app.command(help="Point the episodes at a QuantumStreamer compatible server.")
def patch(
    game_dir: GameDir = None,
    videolist_path: VideoListPath = None,
    server: Annotated[
        str, typer.Option("--server", "-s", help="Host and port of the server.")
    ] = "127.0.0.1:10000",
) -> None:
    try:
        path = videolist_path or _game(game_dir, _interactive()).videolist
        videos = videolist.patch(path, server)
    except (FetchError, OSError) as error:
        _fail(error)
    original = videolist.original_path(path).name
    typer.echo(
        f"Pointed {_count(videos, 'episode')} at http://{server}, keeping the list as {original}"
    )


@videolist_app.command(help="Build the video list from a JSON object of episode IDs and URLs.")
def build(
    input_json: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True, help="JSON file to build from."),
    ],
    game_dir: GameDir = None,
    videolist_path: Annotated[
        Path | None,
        typer.Option(
            dir_okay=False,
            help="File to save the list to instead of the game's list, or its original once "
            "patched, which is the one the episodes are read from.",
        ),
    ] = None,
) -> None:
    try:
        videos = videolist.read_json(input_json)
        path = videolist_path or videolist.unpatched(_game(game_dir, _interactive()).videolist)
        videolist.save(path, videos)
    except (FetchError, OSError) as error:
        _fail(error)
    typer.echo(f"Saved {_count(videos, 'episode')} to {path}")


def _interactive() -> bool:
    # Questions are asked on stdout and answered on stdin, so both have to be the terminal.
    return sys.stdin.isatty() and sys.stdout.isatty()


def _game(game_dir: Path | None, interactive: bool) -> GameFolder:
    if game_dir is None:
        if not interactive:
            raise FetchError("Give the game folder")
        game_dir = prompts.folder("Game folder")
    return GameFolder(game_dir)


def _source_videolist(game_dir: Path | None, path: Path | None) -> Path:
    return path or videolist.unpatched(_game(game_dir, _interactive()).videolist)


def _episode_ids(videos: Mapping[str, str], value: str | None, interactive: bool) -> list[str]:
    if value is None:
        if not interactive:
            return list(videos)
        if picked := prompts.checkbox("Episodes to download", [(id, id) for id in videos]):
            return picked
        raise FetchError("No episodes chosen")
    names = _split(value)
    if selection.ALL in map(str.casefold, names):
        return list(videos)
    known = {episode.casefold(): episode for episode in videos}
    if unknown := [name for name in names if name.casefold() not in known]:
        raise FetchError(f"The video list has no episode {', '.join(unknown)}")
    return [known[name.casefold()] for name in names]


def _fetch(client: HttpClient, videos: Mapping[str, str], workers: int) -> list[Episode]:
    columns = TextColumn("{task.description}"), BarColumn(), MofNCompleteColumn()
    with Progress(*columns, console=_console, transient=True) as progress:
        task = progress.add_task("Fetching manifests", total=len(videos))
        episodes = fetch_episodes(client, videos, workers, partial(progress.advance, task))
    if not episodes:
        raise FetchError("No episode could be fetched")
    return episodes


def _selectors(
    kind: StreamType, value: str | None, episodes: Sequence[Episode], interactive: bool
) -> Sequence[str]:
    per_episode = [_of_type(episode, kind) for episode in episodes]
    tracks = [track for episode_tracks in per_episode for track in episode_tracks]
    if value is not None:
        selectors = _split(value)
        if unknown := selection.unknown(selectors, tracks):
            raise FetchError(
                f"No {kind} track matches {', '.join(unknown)}; the formats command lists them"
            )
        return selectors
    if not interactive or not tracks:
        return selection.DEFAULTS[kind]
    offered = selection.options(per_episode)
    default = selection.defaults(kind, per_episode)
    choices = [(_label(option, len(episodes)), option.selector) for option in offered]
    return prompts.checkbox(
        f"{kind.capitalize()} tracks to download",
        choices,
        default=[option.selector for option in offered if option.selector in default],
    )


def _label(option: selection.Option, episodes: int) -> str:
    label = f"{option.selector}: {option.description}"
    if option.size is not None:
        label += f", ~{decimal(option.size)} per episode"
    if option.episodes < episodes:
        label += f" (in {option.episodes} of {episodes} episodes)"
    return label


def _tracks(episode: Episode, chosen: Mapping[StreamType, Sequence[str]]) -> list[Track]:
    return [
        track
        for kind in StreamType
        for track in selection.select(_of_type(episode, kind), chosen[kind])
    ]


def _of_type(episode: Episode, kind: StreamType) -> list[Track]:
    return [track for track in episode.manifest.tracks if track.type is kind]


def _flag(given: bool | None, ask: bool, question: str, *, default: bool) -> bool:
    if given is not None:
        return given
    return prompts.confirm(question, default) if ask else False


def _log_plan(plan: Sequence[tuple[Episode, Sequence[Track]]]) -> None:
    tracks = [track for _, episode_tracks in plan for track in episode_tracks]
    size = sum(track.estimated_size or 0 for track in tracks)
    about = f", about {decimal(size)}" if size else ""
    log.info("Downloading %s of %s%s", _count(tracks, "track"), _count(plan, "episode"), about)


def _transfer_progress() -> Progress:
    return Progress(
        TextColumn("{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=_console,
    )


@contextmanager
def _progress_task(
    progress: Progress, description: str, total: int | None
) -> Iterator[Callable[[int], None]]:
    """Show a download in `progress` while the context lasts, giving the call that advances it.

    Args:
        progress: The display to show it in.
        description: The download's label.
        total: The bytes it is expected to take, or None when unknown.
    """
    task = progress.add_task(description, total=total)
    try:
        yield partial(progress.advance, task)
    finally:
        progress.remove_task(task)


def _count(items: Sized, noun: str) -> str:
    return f"{len(items)} {noun}{'' if len(items) == 1 else 's'}"


def _split(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _fail(error: Exception | str) -> NoReturn:
    typer.secho(f"Error: {error}", fg="red", err=True)
    raise typer.Exit(1) from error if isinstance(error, Exception) else None

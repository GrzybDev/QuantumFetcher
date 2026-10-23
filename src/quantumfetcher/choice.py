"""The episodes and tracks to download, as the command line names them or a terminal picks them."""

from collections.abc import Mapping, Sequence

from rich.filesize import decimal

from quantumfetcher import prompts, selection
from quantumfetcher.episodes import Episode
from quantumfetcher.errors import FetchError
from quantumfetcher.manifest import StreamType, Track


def episode_ids(videos: Mapping[str, str], value: str | None, interactive: bool) -> list[str]:
    """Resolve the episodes to download to their IDs in the video list.

    Args:
        videos: The video list.
        value: The comma-separated episode IDs or all, or None when left out.
        interactive: Whether to ask which episodes to download when left out, instead of taking
            them all.
    """
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


def selectors(
    kind: StreamType, value: str | None, episodes: Sequence[Episode], interactive: bool
) -> Sequence[str]:
    """Resolve the selectors that pick the tracks of one type to download.

    Args:
        kind: The type of the tracks.
        value: The comma-separated selectors, or None when left out.
        episodes: The episodes to download.
        interactive: Whether to ask which tracks to download when left out, instead of taking
            the default selectors.
    """
    per_episode = [selection.of_type(episode.manifest.tracks, kind) for episode in episodes]
    tracks = [track for episode_tracks in per_episode for track in episode_tracks]
    if value is not None:
        given = _split(value)
        if unknown := selection.unknown(given, tracks):
            raise FetchError(
                f"No {kind} track matches {', '.join(unknown)}; the formats command lists them"
            )
        return given
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


def plan(
    episodes: Sequence[Episode], chosen: Mapping[StreamType, Sequence[str]]
) -> list[tuple[Episode, list[Track]]]:
    """Pair each episode with the tracks the chosen selectors pick in it.

    Args:
        episodes: The episodes to download.
        chosen: The selectors of each track type.
    """
    planned = [(episode, _tracks(episode, chosen)) for episode in episodes]
    if not any(tracks for _, tracks in planned):
        raise FetchError("The selectors pick no tracks to download")
    return planned


def _label(option: selection.Option, episodes: int) -> str:
    """How the terminal offers an option, with its size and how many episodes have it.

    Args:
        option: The option to offer.
        episodes: The number of episodes to download.
    """
    label = f"{option.selector}: {option.description}"
    if option.size is not None:
        label += f", ~{decimal(option.size)} per episode"
    if option.episodes < episodes:
        label += f" (in {option.episodes} of {episodes} episodes)"
    return label


def _tracks(episode: Episode, chosen: Mapping[StreamType, Sequence[str]]) -> list[Track]:
    """The tracks of an episode the selectors pick, video first, then audio, then text.

    Args:
        episode: The episode to pick from.
        chosen: The selectors of each track type.
    """
    return [
        track
        for kind in StreamType
        for track in selection.select(
            selection.of_type(episode.manifest.tracks, kind), chosen[kind]
        )
    ]


def _split(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]

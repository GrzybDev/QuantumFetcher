"""The game's videoList.rmdj: an encrypted JSON object mapping episode IDs to manifest URLs."""

import json
import logging
import shutil
from collections.abc import Mapping
from pathlib import Path

from quantumfetcher.errors import FetchError

log = logging.getLogger(__name__)

_KEY = bytes.fromhex("ba7abb27039b72fd13eb70387e0fcb41e1d0eb54be8f136df0bae22adcfb40f1")


def decode(data: bytes) -> dict[str, str]:
    try:
        return validate(json.loads(_xor(data)))
    except ValueError as error:
        raise FetchError(f"Not a video list: {error}") from error


def encode(videos: Mapping[str, str]) -> bytes:
    return _xor(json.dumps(videos, indent=4).encode())


def validate(videos: object) -> dict[str, str]:
    if not isinstance(videos, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in videos.items()
    ):
        raise FetchError("A video list must map episode IDs to manifest URLs")
    return videos


def load(path: Path) -> dict[str, str]:
    try:
        return decode(path.read_bytes())
    except FetchError as error:
        raise FetchError(f"{path}: {error}") from error


def save(path: Path, videos: Mapping[str, str]) -> None:
    path.write_bytes(encode(videos))


def replace(path: Path, videos: Mapping[str, str]) -> None:
    """Save a list over the one at `path`, keeping the first list it replaces as <name>.old.

    Args:
        path: The list to replace.
        videos: The manifest URL of each episode ID.
    """
    old = path.with_name(f"{path.name}.old")
    if path.exists() and not old.exists():
        shutil.copy2(path, old)
        log.info("Copied %s to %s before replacing it", path.name, old.name)
    save(path, videos)


def read_json(path: Path) -> dict[str, str]:
    try:
        # From bytes, json also reads the UTF-16 and BOM-marked files Windows tools write.
        return validate(json.loads(path.read_bytes()))
    except (ValueError, FetchError) as error:
        raise FetchError(f"{path}: {error}") from error


def patch(path: Path, server: str) -> dict[str, str]:
    """Point every episode of the list at a QuantumStreamer compatible server, keeping the
    game's own list as its original first."""
    original = original_path(path)
    if not original.exists():
        shutil.copy2(path, original)
    videos = {episode: f"http://{server}/{episode}/manifest" for episode in load(original)}
    save(path, videos)
    return videos


def original_path(path: Path) -> Path:
    """Where the game's own list is kept once `path` is patched, as QuantumStreamer expects it."""
    return path.with_stem(f"{path.stem}_original")


def unpatched(path: Path) -> Path:
    """The list with the episodes' own URLs: the kept original once `path` is patched."""
    original = original_path(path)
    return original if original.exists() else path


def _xor(data: bytes) -> bytes:
    return bytes(byte ^ _KEY[index % len(_KEY)] for index, byte in enumerate(data))

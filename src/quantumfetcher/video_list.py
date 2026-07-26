import json
from pathlib import Path
from typing import Annotated
from urllib.parse import unquote, urlparse, urlunparse

import typer
from quantumfetcher.logger import logger
from quantumfetcher.constants import RMDJ_ENCRYPTION_KEY
from quantumfetcher.helpers import get_game_dir, get_videolist_path

videolist_app = typer.Typer(help="Manage the videoList.rmdj manifest file")


@videolist_app.command("dump")
def dump_videolist(
    path: Annotated[
        Path | None,
        typer.Argument(
            help="Path to root game folder", exists=True, dir_okay=True, readable=True
        ),
    ] = None,
    videolist_path: Annotated[
        Path | None,
        typer.Option(
            help="Path to videoList.rmdj file (defaults to data/videoList.rmdj inside game folder)",
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Dump videoList.rmdj to specified JSON file or stdout if '-' is provided",
        ),
    ] = None,
):
    """Dump videoList.rmdj to JSON format"""
    game_path = get_game_dir(path) if not videolist_path else Path()
    vl_path = get_videolist_path(game_path, videolist_path)

    video_list = VideoList(vl_path, is_game_dir=bool(not videolist_path))

    out_path = output
    if out_path == Path("-"):
        out_path = None

    video_list.dump(out_path)


@videolist_app.command("patch")
def patch_videolist(
    path: Annotated[
        Path | None,
        typer.Argument(
            help="Path to root game folder", exists=True, dir_okay=True, readable=True
        ),
    ] = None,
    videolist_path: Annotated[
        Path | None,
        typer.Option(
            help="Path to videoList.rmdj file (defaults to data/videoList.rmdj inside game folder)",
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
    server: Annotated[
        str,
        typer.Option(
            "--server",
            "-s",
            help="Custom streaming server host to patch with",
        ),
    ] = "127.0.0.1:10000",
):
    """Patch videoList.rmdj to point to a custom QuantumStreamer compatible server"""
    game_path = get_game_dir(path) if not videolist_path else Path()
    vl_path = get_videolist_path(game_path, videolist_path)

    video_list = VideoList(vl_path, is_game_dir=bool(not videolist_path))
    video_list.patch(server)


@videolist_app.command("build")
def build_videolist(
    input: Annotated[
        Path,
        typer.Argument(
            help="Path to the JSON file to build from",
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ],
    path: Annotated[
        Path | None,
        typer.Option(
            "--path",
            "-p",
            help="Path to root game folder to save the built rmdj",
            exists=True,
            dir_okay=True,
            readable=True,
        ),
    ] = None,
    videolist_path: Annotated[
        Path | None,
        typer.Option(
            help="Output path for the built videoList.rmdj file (defaults to data/videoList.rmdj inside game folder)",
            file_okay=True,
            dir_okay=False,
            writable=True,
        ),
    ] = None,
):
    """Build videoList.rmdj from a JSON file"""
    game_path = get_game_dir(path) if not videolist_path else Path()
    vl_path = get_videolist_path(game_path, videolist_path)

    VideoList.build(input, vl_path)


class VideoList:
    @property
    def episode_list(self) -> dict[str, str]:
        return self.__videoList

    def __init__(self, path: Path, is_game_dir: bool = False):
        self.__path = path

        if is_game_dir:
            # Check if {filename}_original.rmdj file exist
            # if user already installed custom videoList.rmdj
            # the original one will be stored at {filename}_original.rmdj
            filename_orig = path.with_stem(path.stem + "_original")

            # First, check if videoList_original.rmdj file exist
            if filename_orig.exists():
                path = filename_orig

        self.__load_video_list(path)

    @staticmethod
    def __xor_bytes(src_bytes: bytes) -> bytearray:
        xor_bytes = bytearray()
        for i, byte in enumerate(src_bytes):
            xor_bytes.append(byte ^ RMDJ_ENCRYPTION_KEY[i % len(RMDJ_ENCRYPTION_KEY)])
        return xor_bytes

    def __load_video_list(self, path: Path):
        with open(path, "rb") as f:
            decrypted_list_raw = self.__xor_bytes(f.read())
            self.__videoList = json.loads(decrypted_list_raw)

    def dump(self, dump_path: Path | None = None):
        if dump_path is None:
            logger.print(json.dumps(self.__videoList, indent=4))
            return

        # Dump the videoList to the specified path
        with open(dump_path, "w") as f:
            json.dump(self.__videoList, f, indent=4)

    def patch(self, server_url: str):
        # QuantumStreamer expects client manifest URL to be
        # http://<server_url>/<episode-id>/manifest

        # First, check if the _original.rmdj file exists
        filename_orig = self.__path.with_stem(self.__path.stem + "_original")
        if not filename_orig.exists():
            # If it doesn't exist, create a copy of the current videoList
            self.__path.rename(filename_orig)

        # Now patch the videoList
        for episode_id in self.__videoList.keys():
            # Replace the client manifest URL with the new server URL
            new_client_manifest_url = f"http://{server_url}/{episode_id}/manifest"
            self.__videoList[episode_id] = new_client_manifest_url

        # Dump the patched videoList to string
        patched_video_list = json.dumps(self.__videoList, indent=4).encode()

        # Encrypt the patched videoList
        encrypted_video_list = bytearray()

        for i, char in enumerate(patched_video_list):
            encrypted_video_list.append(
                char ^ RMDJ_ENCRYPTION_KEY[i % len(RMDJ_ENCRYPTION_KEY)]
            )

        # Write the encrypted videoList to the original file
        with open(self.__path, "wb") as f:
            f.write(encrypted_video_list)

    @staticmethod
    def build(json_path: Path, output_path: Path):
        with open(json_path, "r") as f:
            video_list = json.load(f)

        # Encrypt the videoList
        encrypted_video_list = bytearray()

        for i, char in enumerate(json.dumps(video_list, indent=4).encode()):
            encrypted_video_list.append(
                char ^ RMDJ_ENCRYPTION_KEY[i % len(RMDJ_ENCRYPTION_KEY)]
            )

        # Write the encrypted videoList to the output file
        with open(output_path, "wb") as f:
            f.write(encrypted_video_list)

    def get_server_manifest_url(self, episode_id: str) -> str:
        client_manifest_url = self.__videoList.get(episode_id)

        temp_url = urlparse(client_manifest_url)._replace(query="")
        manifestUrl = str(urlunparse(temp_url)).replace("/manifest", "")

        return manifestUrl

    def get_server_manifest_name(self, episode_id: str) -> str:
        server_manifest_url = self.get_server_manifest_url(episode_id)
        return unquote(server_manifest_url.split("/")[-1])

    def get_client_manifest_name(self, episode_id: str) -> str:
        client_manifest_url = self.__videoList.get(episode_id)
        if not client_manifest_url:
            raise ValueError(f"No client manifest URL found for episode {episode_id}")

        parsed_url = urlparse(client_manifest_url)
        return Path(parsed_url.path).name

    def get_media_url(self, episode_id, filename) -> str:
        base_path = self.get_server_manifest_url(episode_id).rsplit("/", 1)[0]
        return f"{base_path}/{filename}"

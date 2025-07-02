import json
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import typer

from quantumfetcher.constants import RMDJ_ENCRYPTION_KEY


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
            typer.echo(json.dumps(self.__videoList, indent=4))
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

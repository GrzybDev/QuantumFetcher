import json
from pathlib import Path
from urllib.parse import unquote, urlparse, urlunparse

from rich.progress import Progress, SpinnerColumn, TextColumn

from quantumfetcher.constants import RMDJ_ENCRYPTION_KEY


class VideoList:

    __videoList: dict[str, str] = {}
    __path: Path

    def __init__(self, path: Path):
        self.__path = path

        # Check if {filename}_original.rmdj file exist
        # if user already installed custom videoList.rmdj
        # the original one will be stored at {filename}_original.rmdj
        filename_orig = path.with_stem(path.stem + "_original")

        # First, check if videoList_original.rmdj file exist
        if filename_orig.exists():
            path = filename_orig

        with Progress(
            SpinnerColumn(finished_text="\u2713"),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            task_id = progress.add_task("Reading video list...")

            with open(path, "rb") as f:
                decrypted_list_raw: bytearray = bytearray()

                while byte := f.read(1):
                    decrypted_list_raw.append(
                        byte[0] ^ RMDJ_ENCRYPTION_KEY[len(decrypted_list_raw) % 32]
                    )

                self.__videoList = json.loads(decrypted_list_raw)

            progress.update(task_id, total=1, completed=True)

    def get_episode_list(self) -> list:
        return list(self.__videoList.keys())

    def get_client_manifest_url(self, episode_id) -> str | None:
        return self.__videoList.get(episode_id)

    def get_server_manifest_url(self, episode_id) -> str | None:
        clientManifestUrl = self.get_client_manifest_url(episode_id)

        temp_url = urlparse(clientManifestUrl)._replace(query="")
        manifestUrl = urlunparse(temp_url).replace("/manifest", "")

        return manifestUrl

    def get_server_manifest_filename(self, episode_id) -> str | None:
        serverManifestUrl = self.get_server_manifest_url(episode_id)

        parsed_url = urlparse(serverManifestUrl)
        filename = parsed_url.path.rsplit("/", 1)[-1]
        return unquote(filename)

    def get_media_url(self, episode_id, filename) -> str | None:
        base_path = self.get_server_manifest_url(episode_id).rsplit("/", 1)[0]
        return f"{base_path}/{filename}"

    def patch_videolist(self, server_url: str):
        # QuantumStreamer server URL expects client manifest URL to be
        # http://<server_url>/<episode-id>/manifest

        # First, check if the _original.rmdj file exists
        filename_orig = self.__path.with_stem(self.__path.stem + "_original")
        if not filename_orig.exists():
            # If it doesn't exist, create a copy of the current videoList
            self.__path.rename(filename_orig)

        # Now patch the videoList
        for episode_id, client_manifest_url in self.__videoList.items():
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

    def dump(self) -> str:
        """
        Returns the video list as a JSON string.
        """
        return json.dumps(self.__videoList, indent=4)

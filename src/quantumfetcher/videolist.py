import json
from pathlib import Path

from rich.progress import Progress, SpinnerColumn, TextColumn

from quantumfetcher.constants import RMDJ_ENCRYPTION_KEY


class VideoList:

    __videoList: dict[str, str] = {}

    def __init__(self, path: Path):
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

    def get_manifest_url(self, episode_id) -> str:
        return self.__videoList[episode_id]

import json
from pathlib import Path

from rich.progress import Progress, SpinnerColumn, TextColumn

from quantumfetcher.constants import RMDJ_ENCRYPTION_KEY


class VideoList:

    def __init__(self, path: Path):
        # Check if {filename}_original.rmdj file exist
        # if user already installed custom videoList.rmdj
        # the original one will be stored at {filename}_original.rmdj
        filename_orig = path.with_stem(path.stem + "_original")

        # First, check if videoList_original.rmdj file exist
        if filename_orig.exists():
            path = filename_orig

        with Progress(transient=True) as progress:
            progress.add_task("Reading video list...", total=None)

            with open(path, "rb") as f:
                decrypted_list_raw: bytearray = bytearray()

                while byte := f.read(1):
                    decrypted_list_raw.append(
                        byte[0] ^ RMDJ_ENCRYPTION_KEY[len(decrypted_list_raw) % 32]
                    )

                self.__videoList = json.loads(decrypted_list_raw)


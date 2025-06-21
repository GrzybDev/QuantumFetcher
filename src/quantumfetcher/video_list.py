import json
from pathlib import Path

from quantumfetcher.constants import RMDJ_ENCRYPTION_KEY


class VideoList:

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

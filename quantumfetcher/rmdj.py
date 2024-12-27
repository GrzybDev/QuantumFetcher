import json
from pathlib import Path

import typer

RMDJ_KEY = [
    0xBA,
    0x7A,
    0xBB,
    0x27,
    0x03,
    0x9B,
    0x72,
    0xFD,
    0x13,
    0xEB,
    0x70,
    0x38,
    0x7E,
    0x0F,
    0xCB,
    0x41,
    0xE1,
    0xD0,
    0xEB,
    0x54,
    0xBE,
    0x8F,
    0x13,
    0x6D,
    0xF0,
    0xBA,
    0xE2,
    0x2A,
    0xDC,
    0xFB,
    0x40,
    0xF1,
]


class RMDJ:

    __videoList: dict[str, str]

    def __init__(self, path: Path):
        self.__videoList = {}
        self.__load(path)

    def __load(self, path: Path):
        with open(path, "rb") as f:
            video_list_bytes = f.read()
            decrypted_video_list = []

            for byte in video_list_bytes:
                decrypted_video_list.append(
                    byte ^ RMDJ_KEY[len(decrypted_video_list) % 32]
                )

            try:
                self.__videoList = json.loads(
                    "".join([chr(byte) for byte in decrypted_video_list])
                )
            except json.JSONDecodeError:
                raise typer.BadParameter(f"Failed to decode video list")

    def get_episodes(self) -> list[str]:
        return list(self.__videoList.keys())

    def get_episode_url(self, episode: str) -> str | None:
        return self.__videoList.get(episode)

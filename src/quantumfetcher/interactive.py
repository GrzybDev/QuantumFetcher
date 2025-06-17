from pathlib import Path

import typer

from quantumfetcher import surveys
from quantumfetcher.enumerators.stream_type import StreamType
from quantumfetcher.flow import DownloadFlow
from quantumfetcher.videolist import VideoList


def InteractiveMain(gamePath: Path, videoList_path: Path, episodes_path: Path):
    videoList = VideoList(gamePath / videoList_path)

    episodes_to_fetch, manifests = surveys.get_episodes(videoList)
    qualities_to_fetch = surveys.get_streams(episodes_to_fetch, manifests)
    extract_subtitles = False

    if qualities_to_fetch[StreamType.Text]:
        extract_subtitles = typer.confirm(
            "Do you want to extract subtitles to editable format?"
        )

    flow = DownloadFlow(
        videoList=videoList,
        manifests=manifests,
        output_path=gamePath / episodes_path,
        extract_subtitles=extract_subtitles,
    )

    flow.download(episodes_to_fetch, qualities_to_fetch)

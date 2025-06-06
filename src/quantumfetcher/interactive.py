from pathlib import Path

from quantumfetcher import surveys
from quantumfetcher.flow import DownloadFlow
from quantumfetcher.videolist import VideoList


def InteractiveMain(gamePath: Path, videoList_path: Path, episodes_path: Path):
    videoList = VideoList(gamePath / videoList_path)

    episodes_to_fetch, manifests = surveys.get_episodes(videoList)
    qualities_to_fetch = surveys.get_streams(episodes_to_fetch, manifests)

    flow = DownloadFlow(
        videoList=videoList, manifests=manifests, output_path=gamePath / episodes_path
    )

    flow.download(episodes_to_fetch, qualities_to_fetch)

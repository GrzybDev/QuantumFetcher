import operator
import sys

import inquirer
import typer
from rich.progress import track

from quantumfetcher.dataclasses.AudioStream import AudioStream
from quantumfetcher.dataclasses.TextStream import TextStream
from quantumfetcher.dataclasses.VideoStream import VideoStream
from quantumfetcher.downloader import fetch_manifest
from quantumfetcher.enumerators.ManifestType import ManifestType
from quantumfetcher.enumerators.StreamType import StreamType


def get_episodes(videoList):
    all_episodes = videoList.get_episode_list()

    # Fetch server and client manifests for all episodes
    manifests = {}
    for episode_id in track(all_episodes, description="Fetching episode manifests..."):
        client_manifest_url = videoList.get_client_manifest_url(episode_id)
        server_manifect_url = videoList.get_server_manifest_url(episode_id)

        if client_manifest_url and server_manifect_url:
            try:
                client_manifest = fetch_manifest(
                    client_manifest_url, ManifestType.Client
                )
                server_manifest = fetch_manifest(
                    server_manifect_url, ManifestType.Server
                )
                manifests[episode_id] = (server_manifest, client_manifest)
            except Exception as e:
                typer.echo(
                    f"Failed to fetch episode {episode_id} manifests! ({e})", err=True
                )
                all_episodes.remove(episode_id)

    questions = [
        inquirer.Checkbox(
            "episodes",
            message="Which episodes you want to download?",
            choices=all_episodes,
            default=[],
        )
    ]

    answers = inquirer.prompt(questions)

    if not answers:
        answers = {"episodes": []}

    return answers["episodes"], manifests


def get_streams(fetch_episodes, manifests):
    if not fetch_episodes:
        typer.echo("No episodes selected. Exiting...")
        sys.exit(0)

    video_set, audio_set, text_set = set(), set(), set()

    def should_process(episode_id):
        return episode_id != "J1 - 4K Test" or len(fetch_episodes) == 1

    for episode_id in fetch_episodes:
        if not should_process(episode_id):
            continue

        manifest = manifests[episode_id][1]
        video_set.update(manifest.list_video_streams())
        audio_set.update(manifest.list_audio_streams())
        text_set.update(manifest.list_text_streams())

    def make_video_streams(streams):
        return sorted(
            [VideoStream(*v) for v in streams],
            key=operator.attrgetter("bitrate"),
            reverse=True,
        )

    def make_audio_streams(streams):
        return sorted(
            [AudioStream(*a) for a in streams],
            key=lambda x: (x.language.name, -x.bitrate),
        )

    def make_text_streams(streams):
        return sorted(
            [TextStream(*t) for t in streams],
            key=lambda x: (x.language.name, -x.bitrate),
        )

    questions = [
        inquirer.Checkbox(
            name=StreamType.Video,
            message="Select video streams to download",
            choices=make_video_streams(video_set),
            default=[],
        ),
        inquirer.Checkbox(
            name=StreamType.Audio,
            message="Select audio streams to download",
            choices=make_audio_streams(audio_set),
            default=[],
        ),
        inquirer.Checkbox(
            name=StreamType.Text,
            message="Select text streams to download",
            choices=make_text_streams(text_set),
            default=[],
        ),
    ]

    return inquirer.prompt(questions)

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
from quantumfetcher.helpers import fetch_manifests, get_quality_levels


def get_episodes(videoList, selected_episodes=None):
    all_episodes = videoList.get_episode_list()

    if not selected_episodes:
        questions = [
            inquirer.Checkbox(
                "episodes",
                message="Which episodes you want to download?",
                choices=all_episodes,
                default=[],
            )
        ]

        answers = inquirer.prompt(questions)
    else:
        answers = {"episodes": selected_episodes}

    if not answers:
        answers = {"episodes": []}

    return answers["episodes"], fetch_manifests(videoList, answers["episodes"])


def get_streams(fetch_episodes, manifests):
    if not fetch_episodes:
        typer.echo("No episodes selected. Exiting...")
        sys.exit(0)

    qualities = get_quality_levels(manifests, fetch_episodes)

    questions = [
        inquirer.Checkbox(
            name=StreamType.Video,
            message="Select video streams to download",
            choices=qualities[StreamType.Video],
            default=[],
        ),
        inquirer.Checkbox(
            name=StreamType.Audio,
            message="Select audio streams to download",
            choices=qualities[StreamType.Audio],
            default=[],
        ),
        inquirer.Checkbox(
            name=StreamType.Text,
            message="Select text streams to download",
            choices=qualities[StreamType.Text],
            default=[],
        ),
    ]

    # Filter out prompts with no choices
    questions = [q for q in questions if q.choices]

    if not questions:
        typer.echo("No streams available for download.", err=True)
        return {}

    answers = inquirer.prompt(questions)

    if not answers:
        answers = {StreamType.Video: [], StreamType.Audio: [], StreamType.Text: []}

    return answers

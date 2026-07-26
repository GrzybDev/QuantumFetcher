from pathlib import Path

import inquirer
import typer

from quantumfetcher.enumerators.stream import StreamType
from quantumfetcher.logger import logger
from quantumfetcher.video_list import VideoList


class Prompt:
    @staticmethod
    def get_game_path() -> Path:
        questions = [
            inquirer.Path(
                "path",
                path_type=inquirer.Path.DIRECTORY,
                message="Enter path to root game folder",
            )
        ]

        answers = inquirer.prompt(questions)

        if answers is None or "path" not in answers:
            raise typer.Abort()

        return Path(answers["path"])

    @staticmethod
    def select_episodes(video_list: VideoList) -> list[str]:
        questions = [
            inquirer.Checkbox(
                "episodes",
                message="Select episodes to fetch (ctrl+a to select all)",
                choices=list(video_list.episode_list.keys()),
            )
        ]
        answers = inquirer.prompt(questions)

        if answers is None or "episodes" not in answers:
            raise typer.Abort()

        return answers["episodes"]

    @staticmethod
    def select_streams(qualities: dict[StreamType, list]) -> dict[StreamType, list]:
        questions = []

        if StreamType.Video in qualities and qualities[StreamType.Video]:
            questions.append(
                inquirer.Checkbox(
                    StreamType.Video,
                    message="Select video resolutions (ctrl+a to select all)",
                    choices=qualities[StreamType.Video],
                )
            )

        if StreamType.Audio in qualities and qualities[StreamType.Audio]:
            questions.append(
                inquirer.Checkbox(
                    StreamType.Audio,
                    message="Select audio languages (ctrl+a to select all)",
                    choices=qualities[StreamType.Audio],
                )
            )

        if StreamType.Text in qualities and qualities[StreamType.Text]:
            questions.append(
                inquirer.Checkbox(
                    StreamType.Text,
                    message="Select text languages (ctrl+a to select all)",
                    choices=qualities[StreamType.Text],
                )
            )

        # Filter out prompts with no choices
        questions = [q for q in questions if q.choices]

        if not questions:
            logger.error("No streams available for download.")
            raise typer.Exit()

        answers = inquirer.prompt(questions)

        if answers is None:
            raise typer.Abort()

        filtered_answers = {
            StreamType.Video: answers.get(StreamType.Video, []),
            StreamType.Audio: answers.get(StreamType.Audio, []),
            StreamType.Text: answers.get(StreamType.Text, []),
        }

        return filtered_answers

    @staticmethod
    def extract_subtitles() -> bool:
        questions = [
            inquirer.Confirm(
                "extract_subtitles",
                message="Do you want to extract subtitles?",
                default=False,
            )
        ]
        answers = inquirer.prompt(questions)

        if answers is None or "extract_subtitles" not in answers:
            raise typer.Abort()

        return answers["extract_subtitles"]

    @staticmethod
    def append_episode_title() -> bool:
        questions = [
            inquirer.Confirm(
                "append_episode_title",
                message="Do you want to append the episode title to the subtitles?",
                default=True,
            )
        ]
        answers = inquirer.prompt(questions)

        if answers is None or "append_episode_title" not in answers:
            raise typer.Abort()

        return answers["append_episode_title"]

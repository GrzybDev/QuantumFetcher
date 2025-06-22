from pathlib import Path

import inquirer
import typer

from quantumfetcher.enumerators.type_stream import StreamType
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
                message="Select episodes to fetch",
                choices=video_list.episode_list.keys(),
            )
        ]
        answers = inquirer.prompt(questions)

        if answers is None or "episodes" not in answers:
            raise typer.Abort()

        return answers["episodes"]

    @staticmethod
    def select_streams(
        qualities: dict[StreamType, list],
        skip_video_prompt: bool,
        skip_audio_prompt: bool,
        skip_text_prompt: bool,
    ):
        questions = []

        if not skip_video_prompt and StreamType.Video in qualities:
            questions.append(
                inquirer.Checkbox(
                    StreamType.Video,
                    message="Select video streams to fetch",
                    choices=qualities[StreamType.Video],
                )
            )

        if not skip_audio_prompt and StreamType.Audio in qualities:
            questions.append(
                inquirer.Checkbox(
                    StreamType.Audio,
                    message="Select audio streams to fetch",
                    choices=qualities[StreamType.Audio],
                )
            )

        if not skip_text_prompt and StreamType.Text in qualities:
            questions.append(
                inquirer.Checkbox(
                    StreamType.Text,
                    message="Select text streams to fetch",
                    choices=qualities[StreamType.Text],
                )
            )

        # Filter out prompts with no choices
        questions = [q for q in questions if q.choices]

        if not questions:
            typer.echo("No streams available for download.", err=True)
            raise typer.Exit()

        answers = inquirer.prompt(questions)

        if answers is None:
            raise typer.Abort()

        filtered_answers = {}
        filtered_answers[StreamType.Video] = answers.get(StreamType.Video, [])
        filtered_answers[StreamType.Audio] = answers.get(StreamType.Audio, [])
        filtered_answers[StreamType.Text] = answers.get(StreamType.Text, [])

        return filtered_answers

    @staticmethod
    def extract_subtitles() -> bool:
        questions = [
            inquirer.Confirm(
                "extract_subtitles",
                message="Do you want to extract subtitles?",
                default=True,
            )
        ]
        answers = inquirer.prompt(questions)

        if answers is None or "extract_subtitles" not in answers:
            raise typer.Abort()

        return answers["extract_subtitles"]

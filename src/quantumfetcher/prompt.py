from pathlib import Path

import inquirer
import typer

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

from pathlib import Path

import inquirer
import typer


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

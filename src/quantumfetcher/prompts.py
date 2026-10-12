"""Questions asked in the terminal about what the command line leaves out."""

import os
from collections.abc import Collection, Sequence
from pathlib import Path

# inquirer's blessed backend warns about each terminal capability it does not know, such as ssupm
# in some Windows terminals, unless told not to before it is imported.
os.environ.setdefault("BLESSED_NOWARN_UNKNOWN_CAPS", "1")

import inquirer


def folder(message: str) -> Path:
    question = inquirer.Path(
        "answer", message=message, path_type=inquirer.Path.DIRECTORY, exists=True
    )
    return Path(_ask(question))


def checkbox(
    message: str, choices: Sequence[tuple[str, str]], default: Collection[str] = ()
) -> list[str]:
    """The values of the (label, value) choices picked."""
    hint = f"{message} (space toggles, ctrl+a selects all, enter confirms)"
    return _ask(inquirer.Checkbox("answer", message=hint, choices=choices, default=list(default)))


def confirm(message: str, default: bool) -> bool:
    return _ask(inquirer.Confirm("answer", message=message, default=default))


def _ask(question: inquirer.questions.Question):
    return inquirer.prompt([question], raise_keyboard_interrupt=True)["answer"]

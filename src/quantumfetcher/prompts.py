"""Questions asked in the terminal about what the command line leaves out.

Ctrl+C while a question is asked raises KeyboardInterrupt, which aborts the command.
"""

from collections.abc import Collection, Sequence
from pathlib import Path

import questionary


def folder(message: str) -> Path:
    question = questionary.path(
        message,
        only_directories=True,
        validate=lambda answer: Path(answer).is_dir() or "Not an existing folder",
    )
    return Path(question.unsafe_ask())


def checkbox(
    message: str, choices: Sequence[tuple[str, str]], default: Collection[str] = ()
) -> list[str]:
    """The values of the (label, value) choices picked."""
    options = [
        questionary.Choice(label, value=value, checked=value in default) for label, value in choices
    ]
    return questionary.checkbox(message, choices=options).unsafe_ask()


def confirm(message: str, default: bool) -> bool:
    return questionary.confirm(message, default=default).unsafe_ask()

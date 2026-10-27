"""Questions asked in the terminal about what the command line leaves out.

Ctrl+C while a question is asked raises KeyboardInterrupt, which aborts the command.
"""

from collections.abc import Collection, Sequence
from pathlib import Path

import questionary


def folder(message: str) -> Path:
    """Ask for an existing folder until one is given.

    Args:
        message: The question to ask.
    """
    question = questionary.path(
        message,
        only_directories=True,
        validate=lambda answer: Path(answer).is_dir() or "Not an existing folder",
    )
    return Path(question.unsafe_ask())


def checkbox(
    message: str, choices: Sequence[tuple[str, str]], default: Collection[str] = ()
) -> list[str]:
    """Ask which of the choices to pick, returning the values picked.

    Args:
        message: The question to ask.
        choices: The (label, value) pairs to pick from.
        default: The values picked to begin with.
    """
    options = [
        questionary.Choice(label, value=value, checked=value in default) for label, value in choices
    ]
    picked: list[str] = questionary.checkbox(message, choices=options).unsafe_ask()
    return picked


def confirm(message: str, default: bool) -> bool:
    """Ask a yes or no question.

    Args:
        message: The question to ask.
        default: The answer Enter gives.
    """
    answer: bool = questionary.confirm(message, default=default).unsafe_ask()
    return answer


def pause(message: str) -> None:
    """Wait until any key is pressed.

    Args:
        message: The message to show while waiting.
    """
    questionary.press_any_key_to_continue(message).unsafe_ask()

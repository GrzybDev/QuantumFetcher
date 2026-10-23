from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from quantumfetcher import prompts

DOWN, SPACE, ENTER = "\x1b[B", " ", "\r"


@contextmanager
def typing(keys: str) -> Iterator[None]:
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        pipe.send_text(keys)
        yield


@pytest.mark.parametrize(
    ("keys", "picked"),
    [
        (ENTER, ["esmx"]),
        (SPACE + ENTER, ["enus", "esmx"]),
        (DOWN + SPACE + DOWN + SPACE + ENTER, ["frfr"]),
    ],
    ids=["default", "another added", "default swapped"],
)
def test_checkbox_starts_from_the_default_and_returns_the_values_picked(
    keys: str, picked: list[str]
) -> None:
    choices = [("English", "enus"), ("Spanish", "esmx"), ("French", "frfr")]
    with typing(keys):
        assert prompts.checkbox("Audio", choices, default=["esmx"]) == picked


@pytest.mark.parametrize(
    ("keys", "default", "answer"),
    [(ENTER, True, True), ("n", True, False), ("y", False, True)],
    ids=["default", "no", "yes"],
)
def test_confirm_takes_the_default_or_the_answer(keys: str, default: bool, answer: bool) -> None:
    with typing(keys):
        assert prompts.confirm("Save?", default) == answer


def test_folder_asks_until_given_an_existing_folder(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with typing(f"{missing}{ENTER}" + "\b" * 8 + ENTER):
        assert prompts.folder("Game folder") == tmp_path


def test_ctrl_c_aborts() -> None:
    with typing("\x03"), pytest.raises(KeyboardInterrupt):
        prompts.confirm("Save?", True)

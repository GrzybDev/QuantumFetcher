from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from quantumfetcher import prompts

ENTER = "\r"


@contextmanager
def typing(keys: str) -> Iterator[None]:
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        pipe.send_text(keys)
        yield


def test_checkbox_starts_from_the_default() -> None:
    choices = [("English", "enus"), ("Spanish", "esmx"), ("French", "frfr")]
    with typing(ENTER):
        assert prompts.checkbox("Audio", choices, default=["esmx"]) == ["esmx"]


def test_folder_asks_until_given_an_existing_folder(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with typing(f"{missing}{ENTER}" + "\b" * 8 + ENTER):
        assert prompts.folder("Game folder") == tmp_path


def test_ctrl_c_aborts() -> None:
    with typing("\x03"), pytest.raises(KeyboardInterrupt):
        prompts.confirm("Save?", True)

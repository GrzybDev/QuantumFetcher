import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from quantumfetcher import prompts

DOWN, SPACE, ENTER = "\x1b[B", " ", "\r"


@contextmanager
def typing(keys: str):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        pipe.send_text(keys)
        yield


class PromptTests(unittest.TestCase):
    def test_checkbox_starts_from_the_default_and_returns_the_values_picked(self):
        choices = [("English", "enus"), ("Spanish", "esmx"), ("French", "frfr")]
        cases = {
            ENTER: ["esmx"],
            SPACE + ENTER: ["enus", "esmx"],
            DOWN + SPACE + DOWN + SPACE + ENTER: ["frfr"],
        }
        for keys, picked in cases.items():
            with self.subTest(keys=keys), typing(keys):
                self.assertEqual(prompts.checkbox("Audio", choices, default=["esmx"]), picked)

    def test_confirm_takes_the_default_or_the_answer(self):
        for keys, default, answer in ((ENTER, True, True), ("n", True, False), ("y", False, True)):
            with self.subTest(keys=keys), typing(keys):
                self.assertEqual(prompts.confirm("Save?", default), answer)

    def test_folder_asks_until_given_an_existing_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing"
            with typing(f"{missing}{ENTER}" + "\b" * 8 + ENTER):
                self.assertEqual(prompts.folder("Game folder"), Path(directory))

    def test_ctrl_c_aborts(self):
        with typing("\x03"), self.assertRaises(KeyboardInterrupt):
            prompts.confirm("Save?", True)


if __name__ == "__main__":
    unittest.main()

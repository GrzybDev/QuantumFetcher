import threading
import time

import pytest

from quantumfetcher.concurrency import results_in_order
from quantumfetcher.errors import FetchError


def test_runs_few_calls_ahead_of_a_slow_one_and_cancels_the_rest_on_leaving() -> None:
    started: list[int] = []

    def call(number: int) -> int:
        started.append(number)
        if number == 0:
            time.sleep(0.05)
        return number

    with results_in_order(call, range(100), 2) as results:
        assert next(results) == 0
    assert len(started) <= 5


def test_waits_for_the_calls_under_way_when_one_fails() -> None:
    other_started = threading.Event()
    running: set[int] = set()

    def call(number: int) -> int:
        running.add(number)
        try:
            if number == 0:
                other_started.wait(5)
                raise FetchError("broken")
            other_started.set()
            time.sleep(0.05)
            return number
        finally:
            running.discard(number)

    with (
        pytest.raises(FetchError, match="broken"),
        results_in_order(call, range(100), 2) as results,
    ):
        list(results)
    assert not running


def test_does_not_wait_for_the_calls_under_way_on_ctrl_c() -> None:
    started, release = threading.Event(), threading.Event()
    finished: list[int] = []

    def call(number: int) -> int:
        started.set()
        release.wait(5)
        finished.append(number)
        return number

    try:
        with pytest.raises(KeyboardInterrupt), results_in_order(call, range(100), 2):
            started.wait(5)
            raise KeyboardInterrupt
        assert not finished
    finally:
        release.set()

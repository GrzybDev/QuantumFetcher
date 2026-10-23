import threading
from collections.abc import Iterator
from unittest.mock import Mock

import pytest
import requests

from quantumfetcher.errors import FetchError
from quantumfetcher.network import HttpClient

URL = "http://cdn.test/x"


def response(status: int, content: bytes = b"") -> requests.Response:
    result = requests.Response()
    result.status_code, result._content, result.url = status, content, URL
    result._content_consumed = True
    return result


def fetch(
    monkeypatch: pytest.MonkeyPatch, *outcomes: requests.Response | Exception, retries: int = 3
) -> tuple[bytes, int, list[float]]:
    session_get = Mock(side_effect=outcomes)
    waits: list[float] = []
    monkeypatch.setattr(requests.Session, "get", session_get)
    monkeypatch.setattr(threading.Event, "wait", waits.append)
    with HttpClient(retries=retries) as client:
        return client.get(URL), session_get.call_count, waits


def test_retries_what_may_pass_with_growing_pauses(monkeypatch: pytest.MonkeyPatch) -> None:
    outcomes = (requests.ConnectionError("reset"), response(503), response(200, b"data"))
    assert fetch(monkeypatch, *outcomes) == (b"data", 3, [1, 2])


def test_gives_up_after_the_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(FetchError, match="reset"):
        fetch(monkeypatch, *[requests.ConnectionError("reset")] * 3, retries=2)


def test_does_not_retry_what_will_not_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(FetchError, match="404"):
        fetch(monkeypatch, response(404), response(200))


def test_stops_a_download_under_way_once_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    client = HttpClient()

    def chunks(response: requests.Response, size: int) -> Iterator[bytes]:
        yield b"first"
        client.close()
        yield b"second"

    monkeypatch.setattr(requests.Session, "get", Mock(return_value=response(200)))
    monkeypatch.setattr(requests.Response, "iter_content", chunks)
    with pytest.raises(FetchError, match="Cancelled"):
        client.get(URL)


def test_stops_once_closed() -> None:
    client = HttpClient()
    client.close()
    with pytest.raises(FetchError, match="Cancelled"):
        client.get(URL)

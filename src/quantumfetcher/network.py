import platform
import threading
from importlib.metadata import version
from types import TracebackType
from typing import Self

import requests
from requests.adapters import HTTPAdapter

from quantumfetcher.errors import FetchError

USER_AGENT = f"QuantumFetcher/{version('quantumfetcher')} ({platform.system()})"

_TRANSIENT_STATUSES = {408, 429, 500, 502, 503, 504}
_MAX_BACKOFF_SECONDS = 30
_CHUNK_SIZE = 64 * 1024


class HttpClient:
    """Retries failures that may pass, until it is closed."""

    def __init__(self, retries: int = 10, connections: int = 8, timeout: float = 30) -> None:
        self._retries = retries
        self._timeout = timeout
        self._closed = threading.Event()
        self._session = requests.Session()
        self._session.headers["User-Agent"] = USER_AGENT
        adapter = HTTPAdapter(pool_maxsize=connections)
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

    def get(self, url: str) -> bytes:
        attempt = 0
        while not self._closed.is_set():
            try:
                with self._session.get(url, timeout=self._timeout, stream=True) as response:
                    response.raise_for_status()
                    return self._read(response)
            except requests.RequestException as error:
                if attempt >= self._retries or not _transient(error):
                    raise FetchError(str(error)) from error
            self._closed.wait(min(2**attempt, _MAX_BACKOFF_SECONDS))
            attempt += 1
        raise FetchError("Cancelled")

    def _read(self, response: requests.Response) -> bytes:
        # A piece at a time, so that closing stops the downloads already under way too.
        content = bytearray()
        for chunk in response.iter_content(_CHUNK_SIZE):
            if self._closed.is_set():
                raise FetchError("Cancelled")
            content += chunk
        return bytes(content)

    def close(self) -> None:
        """Stop every request, including the ones waiting to be retried on other threads."""
        self._closed.set()
        self._session.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def _transient(error: requests.RequestException) -> bool:
    if isinstance(error, requests.HTTPError):
        return error.response is not None and error.response.status_code in _TRANSIENT_STATUSES
    return isinstance(
        error,
        requests.ConnectionError | requests.Timeout | requests.exceptions.ChunkedEncodingError,
    )

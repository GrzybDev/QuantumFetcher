import threading
import unittest
from unittest.mock import patch

import requests

from quantumfetcher.errors import FetchError
from quantumfetcher.network import HttpClient


def response(status: int, content: bytes = b"") -> requests.Response:
    result = requests.Response()
    result.status_code, result._content, result.url = status, content, "http://cdn.test/x"
    result._content_consumed = True
    return result


class HttpClientTests(unittest.TestCase):
    def get(self, *outcomes, retries=3):
        client = HttpClient(retries=retries)
        waits = []
        with (
            patch.object(requests.Session, "get", side_effect=outcomes) as get,
            patch.object(threading.Event, "wait", side_effect=waits.append),
        ):
            try:
                return client.get("http://cdn.test/x"), get.call_count, waits
            finally:
                client.close()

    def test_retries_what_may_pass_with_growing_pauses(self):
        outcomes = (requests.ConnectionError("reset"), response(503), response(200, b"data"))
        self.assertEqual(self.get(*outcomes), (b"data", 3, [1, 2]))

    def test_gives_up_after_the_retries(self):
        with self.assertRaisesRegex(FetchError, "reset"):
            self.get(*[requests.ConnectionError("reset")] * 3, retries=2)

    def test_does_not_retry_what_will_not_pass(self):
        with self.assertRaisesRegex(FetchError, "404"):
            self.get(response(404), response(200))

    def test_stops_a_download_under_way_once_closed(self):
        client = HttpClient()

        def chunks(response, size):
            yield b"first"
            client.close()
            yield b"second"

        with (
            patch.object(requests.Session, "get", return_value=response(200)),
            patch.object(requests.Response, "iter_content", chunks),
            self.assertRaisesRegex(FetchError, "Cancelled"),
        ):
            client.get("http://cdn.test/x")

    def test_stops_once_closed(self):
        client = HttpClient()
        client.close()
        with self.assertRaisesRegex(FetchError, "Cancelled"):
            client.get("http://cdn.test/x")


if __name__ == "__main__":
    unittest.main()

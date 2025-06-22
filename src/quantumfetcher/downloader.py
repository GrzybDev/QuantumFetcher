import requests
from requests.adapters import HTTPAdapter, Retry

from quantumfetcher.constants import USER_AGENT
from quantumfetcher.enumerators.type_manifest import ManifestType
from quantumfetcher.manifests.base import BaseManifest
from quantumfetcher.manifests.client import ClientManifest
from quantumfetcher.manifests.server import ServerManifest


class Downloader:

    def __init__(self):
        self.__session = requests.Session()
        self.__session.headers.update({"User-Agent": USER_AGENT})

        retries = Retry(total=10, backoff_factor=3)

        self.__session.mount("http://", HTTPAdapter(max_retries=retries))

    def __fetch_file(self, url: str) -> str:
        headers = self.__session.headers.copy()  # type: ignore
        headers["Accept-Encoding"] = "deflate"

        r = requests.get(url, headers=headers)
        r.raise_for_status()

        return r.content.decode()

    def fetch_manifest(
        self, manifest_type: ManifestType, manifest_url: str
    ) -> BaseManifest:
        content = self.__fetch_file(manifest_url)

        match manifest_type:
            case ManifestType.Client:
                return ClientManifest(content)
            case ManifestType.Server:
                return ServerManifest(content)

from urllib.parse import urlparse, urlunparse

import requests

from quantumfetcher.enumerators.ManifestType import ManifestType
from quantumfetcher.manifests.client import ClientManifest
from quantumfetcher.manifests.server import ServerManifest

USER_AGENT = "Malibu/1.0"


def fetch_manifest(
    manifestUrl: str, manifestType: ManifestType
) -> ClientManifest | ServerManifest:
    match manifestType:
        case ManifestType.Client:
            return __fetch_client_manifest(manifestUrl)
        case ManifestType.Server:
            temp_url = urlparse(manifestUrl)._replace(query="")
            manifestUrl = urlunparse(temp_url).replace("/manifest", "")

            return __fetch_server_manifest(manifestUrl)


def __fetch_file(fileUrl) -> str:
    r = requests.get(
        fileUrl, headers={"Accept-Encoding": "deflate", "User-Agent": USER_AGENT}
    )

    r.raise_for_status()
    return r.content.decode()


def __fetch_client_manifest(manifestUrl) -> ClientManifest:
    content = __fetch_file(manifestUrl)
    manifest = ClientManifest(content)
    return manifest


def __fetch_server_manifest(manifestUrl) -> ServerManifest:
    content = __fetch_file(manifestUrl)
    manifest = ServerManifest(content)
    return manifest

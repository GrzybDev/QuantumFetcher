from math import ceil
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter, Retry

from quantumfetcher.enumerators.manifest_type import ManifestType
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


def download_media(mediaUrl: str, chunks: int, outputPath: Path, progress):
    progress_media = progress.add_task(f"Downloading {outputPath.name}...")

    with requests.head(mediaUrl) as r:
        contentLength = int(r.headers["Content-Length"])

    progress.update(progress_media, total=contentLength)

    chunkSize = max(
        ceil(contentLength / chunks), 1024 * 1024
    )  # Segment-ish size or 1MB

    if outputPath.exists():
        # Resume from where we left
        currentRange = outputPath.stat().st_size
    else:
        currentRange = 0

    progress.update(progress_media, completed=currentRange)

    with open(outputPath, "ab") as f:
        s = requests.Session()
        retries = Retry(total=10, backoff_factor=1)
        s.mount("http://", HTTPAdapter(max_retries=retries))

        while currentRange < contentLength:
            endRange = min(currentRange + chunkSize, contentLength)

            headers = {
                "User-Agent": USER_AGENT,
                "X-MS-Range": f"bytes={currentRange}-{endRange}",
            }

            with s.get(mediaUrl, headers=headers, stream=True) as r:
                r.raise_for_status()

                dlBytes = 0

                for chunk in r.iter_content(chunk_size=1024):
                    f.write(chunk)
                    currentRange += len(chunk)
                    dlBytes += len(chunk)

                progress.update(progress_media, advance=dlBytes)

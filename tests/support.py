import io
import re
import struct
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from pathlib import Path

from quantumfetcher.errors import FetchError
from quantumfetcher.manifest import ClientManifest, Track
from quantumfetcher.mp4 import TrackWriter
from quantumfetcher.network import HttpClient

MANIFEST_URL = "http://cdn.test/quantum/J1A.ism/manifest?tkn=secret"
CHUNK = 20_000_000
SPS = bytes.fromhex("6742c01eab40")
PPS = bytes.fromhex("68ce3c80")
VIDEO = {2_000_000: (1280, 720), 500_000: (640, 360)}
AUDIO = {"enus": "eng", "esmx": "spa"}
TEXT = {"enus_captions": "eng", "eses_captions": "spa"}
KEY = bytes.fromhex("ba7abb27039b72fd13eb70387e0fcb41e1d0eb54be8f136df0bae22adcfb40f1")
SMIL = "{http://www.w3.org/2001/SMIL20/Language}"


def encrypt(data: bytes) -> bytes:
    return bytes(byte ^ KEY[index % len(KEY)] for index, byte in enumerate(data))


def client_manifest(chunks: int = 3) -> bytes:
    """A client manifest shaped like the episodes' own, with every chunk lasting CHUNK."""
    timeline = "".join(f'<c n="{number}" d="{CHUNK}"/>' for number in range(chunks))
    codec = (b"\0\0\0\1" + SPS + b"\0\0\0\1" + PPS).hex().upper()
    levels = "".join(
        f'<QualityLevel Index="{index}" Bitrate="{bitrate}" FourCC="H264" MaxWidth="{width}" '
        f'MaxHeight="{height}" CodecPrivateData="{codec}"/>'
        for index, (bitrate, (width, height)) in enumerate(VIDEO.items())
    )
    streams = [
        f'<StreamIndex Type="video" Chunks="{chunks}" QualityLevels="{len(VIDEO)}" '
        'MaxWidth="1280" MaxHeight="720" DisplayWidth="1280" DisplayHeight="720" '
        f'Url="QualityLevels({{bitrate}})/Fragments(video={{start time}})">{levels}{timeline}'
        "</StreamIndex>"
    ]
    for name, language in AUDIO.items():
        streams.append(
            f'<StreamIndex Type="audio" Name="{name}" Language="{language}" Chunks="{chunks}" '
            f'QualityLevels="1" Url="QualityLevels({{bitrate}})/Fragments({name}={{start time}})">'
            '<QualityLevel Index="0" Bitrate="256000" FourCC="AACL" SamplingRate="48000" '
            f'Channels="6" BitsPerSample="16" CodecPrivateData="11B0"/>{timeline}</StreamIndex>'
        )
    for name, language in TEXT.items():
        streams.append(
            f'<StreamIndex Type="text" Name="{name}" Language="{language}" Subtype="CAPT" '
            f'Chunks="{chunks}" QualityLevels="1" '
            f'Url="QualityLevels({{bitrate}})/Fragments({name}={{start time}})">'
            f'<QualityLevel Index="0" Bitrate="256000" FourCC="TTML"/>{timeline}</StreamIndex>'
        )
    return (
        '<?xml version="1.0" encoding="utf-8"?><SmoothStreamingMedia MajorVersion="2" '
        f'MinorVersion="0" Duration="{chunks * CHUNK}">{"".join(streams)}</SmoothStreamingMedia>'
    ).encode()


def episode_manifest(chunks: int = 3) -> ClientManifest:
    """The parsed client_manifest.

    Args:
        chunks: The number of fragments of each track.
    """
    return ClientManifest.parse(MANIFEST_URL, client_manifest(chunks))


def track(name: str, bitrate: int = 256000, chunks: int = 3) -> Track:
    """The track of episode_manifest with this stream name and bitrate.

    Args:
        name: The stream name, such as video or enus.
        bitrate: The bitrate of the track's quality level.
        chunks: The number of fragments of each track.
    """
    return next(
        track
        for track in episode_manifest(chunks).tracks
        if (track.name, track.bitrate) == (name, bitrate)
    )


def fragment_url(name: str, bitrate: int, start_time: int) -> str:
    return (
        "http://cdn.test/quantum/J1A.ism/"
        f"QualityLevels({bitrate})/Fragments({name}={start_time})?tkn=secret"
    )


def box(kind: bytes, *payload: bytes) -> bytes:
    content = b"".join(payload)
    return struct.pack(">I4s", 8 + len(content), kind) + content


def fragment(payload: bytes, track_id: int = 1) -> bytes:
    """A movie fragment like the server sends: moof with mfhd and traf/tfhd, then mdat."""
    tfhd = box(b"tfhd", struct.pack(">II", 0, track_id))
    moof = box(b"moof", box(b"mfhd", struct.pack(">II", 0, 1)), box(b"traf", tfhd))
    return moof + box(b"mdat", payload)


def write_track(track: Track, fragments: Sequence[bytes], file: io.BytesIO | None = None) -> bytes:
    """The bytes of a finished track file, carrying on after the whole fragments `file` holds.

    Args:
        track: The track the file holds.
        fragments: Every fragment of the track, as the server sends them.
        file: The file to carry on, or None to write a new one.
    """
    file = file or io.BytesIO()
    writer = TrackWriter(file, track)
    for data in fragments[writer.fragments :]:
        writer.append(data)
    writer.finish()
    return file.getvalue()


def ttml(*paragraphs: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?><tt xml:lang="eng" '
        f'xmlns="http://www.w3.org/ns/ttml"><body><div>{"".join(paragraphs)}</div></body></tt>'
    ).encode()


def caption(begin: str, end: str, text: str) -> str:
    return f'<p begin="{begin}" end="{end}" region="speaker"><span>{text}</span></p>'


def episode_responses(chunks: int = 3) -> dict[str, bytes]:
    """The manifest and every fragment of an episode: media fragments hold their own URL and
    caption fragments a line naming their stream and number."""
    responses = {MANIFEST_URL: client_manifest(chunks)}
    starts = [number * CHUNK for number in range(chunks)]
    tracks = [("video", bitrate) for bitrate in VIDEO] + [(name, 256000) for name in AUDIO]
    for name, bitrate in tracks:
        for start in starts:
            url = fragment_url(name, bitrate, start)
            responses[url] = fragment(url.encode())
    for name in TEXT:
        for number, start in enumerate(starts):
            line = caption("00:00:00.500", "00:00:01.500", f"{name} {number}")
            responses[fragment_url(name, 256000, start)] = fragment(ttml(line))
    return responses


def files(folder: Path) -> list[str]:
    """The sorted names of what `folder` holds.

    Args:
        folder: The folder to list.
    """
    return sorted(path.name for path in folder.iterdir())


def quantumstreamer_index(data: bytes) -> dict[str, int]:
    """The offset of each fragment by its time, read the way QuantumStreamer's preloadTrack does.

    Args:
        data: A whole track file.
    """
    mfro_size = int.from_bytes(data[-4:])
    mfra = data[-mfro_size:]
    assert int.from_bytes(mfra[:4]) == mfro_size and mfra[4:8] == b"mfra"
    assert mfra[12:16] == b"tfra"
    version, (sizes, count) = mfra[16], struct.unpack(">II", mfra[24:32])
    entry = ">QQ" if version == 1 else ">II"
    numbers = ((sizes & 0x3F) >> 4) + ((sizes & 0xC) >> 2) + (sizes & 0x3) + 3
    position = 32
    index: dict[str, int] = {}
    for _ in range(count):
        time, offset = struct.unpack_from(entry, mfra, position)
        position += struct.calcsize(entry) + numbers
        index[str(time)] = offset
    return index


def served_locally(folder: Path) -> tuple[int, int]:
    """Replay QuantumStreamer's lookups for the fragments an episode folder's manifests offer.

    Args:
        folder: The episode folder.

    Returns:
        The number of fragment requests it would serve from the folder's files and the number
        it would fetch from the server.
    """
    (ism,) = folder.glob("*.ism")
    root = ET.parse(ism).getroot()
    (meta,) = root.findall(f"{SMIL}head/{SMIL}meta[@name='clientManifestRelativePath']")
    media: dict[str, dict[str, int]] = {}
    for tag in ("video", "audio", "textstream"):
        for element in root.iter(f"{SMIL}{tag}"):
            name = "video"
            if tag != "video":
                (param,) = element.findall(f"{SMIL}param[@name='trackName']")
                name = param.attrib["value"]
            index = quantumstreamer_index((folder / element.attrib["src"]).read_bytes())
            media[f"{name}_{element.attrib['systemBitrate']}"] = index
    served = fetched = 0
    for stream in ET.parse(folder / meta.attrib["content"]).getroot().findall("StreamIndex"):
        (name,) = re.findall(r"Fragments\((\w+)=", stream.attrib["Url"])
        times: list[int] = []
        time = 0
        for chunk in stream.findall("c"):
            times.append(time)
            time += int(chunk.attrib["d"])
        for level in stream.findall("QualityLevel"):
            index = media.get(f"{name}_{level.attrib['Bitrate']}", {})
            served += sum(str(time) in index for time in times)
            fetched += sum(str(time) not in index for time in times)
    return served, fetched


class FakeClient(HttpClient):
    """An HttpClient answering from URLs mapped to bodies or errors instead of the network."""

    def __init__(self, responses: Mapping[str, bytes | Exception]) -> None:
        """Answer with `responses`, and like a server without the file for other URLs.

        Args:
            responses: The body or error for each URL.
        """
        super().__init__()
        self.responses = dict(responses)
        self.requests: list[str] = []

    def get(self, url: str) -> bytes:
        self.requests.append(url)
        response = self.responses.get(url, FetchError(f"404 Client Error: Not Found for {url}"))
        if isinstance(response, Exception):
            raise response
        return response

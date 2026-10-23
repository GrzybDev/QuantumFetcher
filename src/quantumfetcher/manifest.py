import re
import xml.etree.ElementTree as ET
from collections.abc import Collection, Iterable, Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Self
from urllib.parse import urljoin, urlsplit

from quantumfetcher.errors import FetchError

DEFAULT_TIMESCALE = 10_000_000

_BITRATE = re.compile(r"\{bitrate\}", re.IGNORECASE)
_START_TIME = re.compile(r"\{start[ _]time\}", re.IGNORECASE)
_SMIL = "http://www.w3.org/2001/SMIL20/Language"


class StreamType(StrEnum):
    VIDEO = "video"
    AUDIO = "audio"
    TEXT = "text"


_SMIL_TAGS = {StreamType.VIDEO: "video", StreamType.AUDIO: "audio", StreamType.TEXT: "textstream"}


@dataclass(frozen=True, slots=True)
class Track:
    """A quality level of a stream: what one track file holds."""

    type: StreamType
    name: str
    language: str | None
    bitrate: int
    fourcc: str
    codec_private_data: bytes
    width: int | None
    height: int | None
    sampling_rate: int | None
    channels: int | None
    bits_per_sample: int | None
    nal_unit_length: int
    timescale: int
    start_times: tuple[int, ...]
    duration: int
    url_template: str

    @property
    def locale(self) -> str:
        """The locale the stream is named after, such as enus for both enus and enus_captions."""
        return self.name.partition("_")[0]

    @property
    def label(self) -> str:
        if self.type is StreamType.VIDEO:
            return f"video {self.height}p {self.bitrate // 1000} kbps"
        return f"{self.type} {self.name}"

    @property
    def estimated_size(self) -> int | None:
        # Caption tracks declare a bitrate far above what their few words take.
        if self.type is StreamType.TEXT:
            return None
        return self.bitrate * self.duration // self.timescale // 8

    def fragment_url(self, start_time: int) -> str:
        return _START_TIME.sub(str(start_time), self.url_template)


@dataclass(frozen=True)
class ClientManifest:
    url: str
    xml: bytes
    tracks: tuple[Track, ...]

    @classmethod
    def parse(cls, url: str, xml: bytes) -> Self:
        try:
            root = ET.fromstring(xml)
            if root.tag != "SmoothStreamingMedia":
                raise FetchError(f"Expected a Smooth Streaming manifest, not {root.tag}")
            timescale = int(root.get("TimeScale", DEFAULT_TIMESCALE))
            tracks = tuple(
                track
                for stream in root.findall("StreamIndex")
                for track in _tracks(stream, url, timescale)
            )
        except (ET.ParseError, KeyError, ValueError) as error:
            raise FetchError(f"Invalid manifest {url}: {error!r}") from error
        return cls(url, xml, tracks)

    def local_copy(self, tracks: Collection[Track]) -> bytes:
        """This manifest offering only `tracks`, for QuantumStreamer to serve with their files."""
        kept = {(track.type, track.name, track.bitrate) for track in tracks}
        root = ET.fromstring(self.xml)
        for stream in root.findall("StreamIndex"):
            for level in stream.findall("QualityLevel"):
                if (stream.get("Type"), _name(stream), int(level.get("Bitrate", 0))) not in kept:
                    stream.remove(level)
            levels = stream.findall("QualityLevel")
            if not levels:
                root.remove(stream)
                continue
            for index, level in enumerate(levels):
                level.set("Index", str(index))
            stream.set("QualityLevels", str(len(levels)))
            for size in ("MaxWidth", "MaxHeight"):
                if stream.get(size) is not None:
                    stream.set(size, str(max(int(level.get(size, 0)) for level in levels)))
        return _serialize(root)


def server_manifest(client_manifest: str, files: Iterable[tuple[Track, str]]) -> bytes:
    """A SMIL server manifest naming the client manifest and the file of each track.

    QuantumStreamer serves a fragment from the file whose element has the requested bitrate and,
    unless it is video, the requested track name.
    """
    root = ET.Element("smil", xmlns=_SMIL)
    head = ET.SubElement(root, "head")
    ET.SubElement(head, "meta", name="clientManifestRelativePath", content=client_manifest)
    switch = ET.SubElement(ET.SubElement(root, "body"), "switch")
    for track, file_name in files:
        element = ET.SubElement(
            switch, _SMIL_TAGS[track.type], src=file_name, systemBitrate=str(track.bitrate)
        )
        if track.language:
            element.set("systemLanguage", track.language)
        ET.SubElement(element, "param", name="trackName", value=track.name, valuetype="data")
    return _serialize(root)


def _tracks(stream: ET.Element, manifest_url: str, timescale: int) -> Iterator[Track]:
    try:
        stream_type = StreamType(stream.get("Type", ""))
    except ValueError:
        return
    stream_timescale = int(stream.get("TimeScale", timescale))
    start_times, end = _timeline(stream)
    template = _resolve(manifest_url, stream.attrib["Url"])
    for level in stream.findall("QualityLevel"):
        bitrate = int(level.attrib["Bitrate"])
        yield Track(
            type=stream_type,
            name=_name(stream),
            language=stream.get("Language"),
            bitrate=bitrate,
            fourcc=level.get("FourCC", ""),
            codec_private_data=bytes.fromhex(level.get("CodecPrivateData", "")),
            width=_optional_int(level.get("MaxWidth") or level.get("Width")),
            height=_optional_int(level.get("MaxHeight") or level.get("Height")),
            sampling_rate=_optional_int(level.get("SamplingRate")),
            channels=_optional_int(level.get("Channels")),
            bits_per_sample=_optional_int(level.get("BitsPerSample")),
            nal_unit_length=int(level.get("NALUnitLengthField", 4)),
            timescale=stream_timescale,
            start_times=start_times,
            duration=end,
            url_template=_BITRATE.sub(str(bitrate), template),
        )


def _name(stream: ET.Element) -> str:
    """The name fragment URLs and QuantumStreamer know the stream by."""
    return stream.get("Name") or stream.get("Type") or ""


def _timeline(stream: ET.Element) -> tuple[tuple[int, ...], int]:
    """The start time of each fragment of `stream` and the time the last one ends."""
    start_times = []
    time = 0
    for chunk in stream.findall("c"):
        time = int(chunk.get("t", time))
        for _ in range(int(chunk.get("r", 1))):
            start_times.append(time)
            time += int(chunk.attrib["d"])
    return tuple(start_times), time


def _resolve(manifest_url: str, path: str) -> str:
    """The URL of `path` next to the manifest, keeping the manifest's query like the game does."""
    url = urljoin(manifest_url, path)
    query = urlsplit(manifest_url).query
    return f"{url}?{query}" if query else url


def _optional_int(value: str | None) -> int | None:
    return None if value is None else int(value)


def _serialize(root: ET.Element) -> bytes:
    """The UTF-8 XML document of `root`, indented in place first.

    Args:
        root: The document's root element.
    """
    ET.indent(root)
    xml: bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return xml

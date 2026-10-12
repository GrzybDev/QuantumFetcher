import re
import xml.etree.ElementTree as ET
from collections.abc import Collection, Iterable, Iterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Self
from urllib.parse import urljoin, urlsplit

import requests

from quantumfetcher.constants import SMIL_NS, USER_AGENT
from quantumfetcher.enumerators.language import LanguageMap
from quantumfetcher.errors import FetchError
from quantumfetcher.logger import logger

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
        ET.indent(root)
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)


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
    ET.indent(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _tracks(stream: ET.Element, manifest_url: str, timescale: int) -> Iterator[Track]:
    try:
        stream_type = StreamType(stream.get("Type"))
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
    return stream.get("Name") or stream.get("Type", "")


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


def generate_local_manifests(
    manifest_url: str,
    episode_dir: Path,
    base_name: str,
    video_format_ids: list[str],
    audio_format_ids: list[str],
    text_langs: list[str],
):
    audio_langs = (
        [fmt.split("-")[0] for fmt in audio_format_ids] if audio_format_ids else []
    )

    client_resp = requests.get(manifest_url, headers={"User-Agent": USER_AGENT})
    client_resp.raise_for_status()

    # Generate Client Manifest (.ismc)
    client_manifest_path = episode_dir / f"{base_name}.ismc"

    c_root = ET.fromstring(client_resp.text)

    streams_to_remove = []

    for stream in c_root.findall("StreamIndex"):
        stream_type = stream.get("Type")
        stream_name = stream.get("Name", "")

        if stream_type == "video":
            qls_to_remove = []
            max_width = max_height = ql_idx = 0

            for ql in stream.findall("QualityLevel"):
                r_b = ql.get("Bitrate", "-1")
                k_b = str(int(r_b) // 1000) if r_b.isdigit() else "-1"

                if r_b in video_format_ids or k_b in video_format_ids:
                    max_width = max(max_width, int(ql.get("MaxWidth", 0)))
                    max_height = max(max_height, int(ql.get("MaxHeight", 0)))
                    ql.set("Index", str(ql_idx))
                    ql_idx += 1
                else:
                    qls_to_remove.append(ql)

            for ql in qls_to_remove:
                stream.remove(ql)

            if ql_idx == 0:
                streams_to_remove.append(stream)
            else:
                stream.set("QualityLevels", str(ql_idx))
                stream.set("MaxWidth", str(max_width))
                stream.set("MaxHeight", str(max_height))
                stream.set("DisplayWidth", str(max_width))
                stream.set("DisplayHeight", str(max_height))

                # Re-index chunks
                for idx, chunk in enumerate(stream.findall("c")):
                    chunk.set("n", str(idx))

        elif stream_type == "audio":
            if not any(
                stream_name.startswith(lang_prefix) for lang_prefix in audio_langs
            ):
                streams_to_remove.append(stream)
            else:
                for idx, chunk in enumerate(stream.findall("c")):
                    chunk.set("n", str(idx))

        elif stream_type == "text":
            if not any(
                stream_name.startswith(lang_prefix) for lang_prefix in text_langs
            ):
                streams_to_remove.append(stream)
            else:
                for idx, chunk in enumerate(stream.findall("c")):
                    chunk.set("n", str(idx))

    for stream in streams_to_remove:
        c_root.remove(stream)

    tree = ET.ElementTree(c_root)
    ET.indent(tree, space="  ", level=0)
    tree.write(client_manifest_path, xml_declaration=True, encoding="UTF-8")

    logger.log(f"Saved client manifest: {client_manifest_path.name}")

    # Generate Server Manifest (.ism)
    server_manifest_path = episode_dir / f"{base_name}.ism"

    root = ET.Element("smil", xmlns=SMIL_NS["smil"])
    head = ET.SubElement(root, "head")
    ET.SubElement(
        head,
        "meta",
        name="clientManifestRelativePath",
        content=client_manifest_path.name,
    )
    ET.SubElement(head, "meta", name="title", content=base_name)

    body = ET.SubElement(root, "body")
    switch = ET.SubElement(body, "switch")

    # Extract raw bitrates from client manifest
    raw_vids = []
    try:
        for ql in c_root.findall(".//QualityLevel"):
            r_b = ql.get("Bitrate", "-1")
            k_b = str(int(r_b) // 1000) if r_b.isdigit() else "-1"
            if r_b in video_format_ids or k_b in video_format_ids:
                raw_vids.append(r_b)
        raw_vids = list(set(raw_vids))
    except Exception:
        raw_vids = video_format_ids

    for v_id in raw_vids:
        kbps_id = str(int(v_id) // 1000) if v_id.isdigit() else v_id
        vid = ET.SubElement(
            switch,
            "video",
            src=f"{base_name}_{kbps_id}.ismv",
            systemBitrate=v_id,
        )
        ET.SubElement(vid, "param", name="trackID", value="1", valuetype="data")

    for fmt_id in audio_format_ids:
        a_lang = fmt_id.split("-")[0] if "-" in fmt_id else fmt_id
        a_bitrate = str(int(fmt_id.split("-")[1]) * 1000) if "-" in fmt_id else "256000"
        yt_lang = LanguageMap.get_value(a_lang, a_lang) or a_lang

        aud = ET.SubElement(
            switch,
            "audio",
            src=f"{base_name}_{a_lang}.isma",
            systemBitrate=a_bitrate,
            systemLanguage=yt_lang,
        )
        ET.SubElement(aud, "param", name="trackID", value="1", valuetype="data")
        ET.SubElement(aud, "param", name="trackName", value=a_lang, valuetype="data")
        ET.SubElement(aud, "param", name="Subtype", value="AACL", valuetype="data")
        ET.SubElement(
            aud, "param", name="timeScale", value="10000000", valuetype="data"
        )

    for t_lang in text_langs:
        yt_lang = LanguageMap.get_value(t_lang, t_lang) or t_lang
        txt = ET.SubElement(
            switch,
            "textstream",
            src=f"{base_name}_{t_lang}_cc.ismt",
            systemBitrate="256000",
            systemLanguage=yt_lang,
        )
        ET.SubElement(txt, "param", name="trackID", value="1", valuetype="data")
        ET.SubElement(txt, "param", name="Subtype", value="CAPT", valuetype="data")
        ET.SubElement(txt, "param", name="FourCC", value="TTML", valuetype="data")
        ET.SubElement(
            txt,
            "param",
            name="trackName",
            value=f"{t_lang}_captions",
            valuetype="data",
        )
        ET.SubElement(
            txt, "param", name="timeScale", value="10000000", valuetype="data"
        )

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ", level=0)
    tree.write(server_manifest_path, encoding="utf-8", xml_declaration=True)
    logger.log(f"Generated local server manifest: {server_manifest_path.name}")

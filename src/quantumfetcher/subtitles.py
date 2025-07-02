import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import typer

from quantumfetcher.constants import TTML_NS


def __get_fragment_offsets(reader, path):
    reader.seek(-4, os.SEEK_END)
    mfroSize = int.from_bytes(reader.read(4))

    reader.seek(-mfroSize, os.SEEK_END)

    mfraBlockSize = int.from_bytes(reader.read(4))

    if mfraBlockSize != mfroSize:
        typer.echo(
            f"Cannot extract subtitles! Invalid mfro block size in track file {path} (Expected: {mfroSize}, Got: {mfraBlockSize}).",
            err=True,
        )
        return

    mfraMagic = reader.read(4)

    if mfraMagic != b"mfra":
        typer.echo(
            f"Cannot extract subtitles! Invalid mfra magic in track file {path} (Expected: mfra, Got: {mfraMagic}).",
            err=True,
        )
        return

    reader.seek(4, os.SEEK_CUR)
    tfraMagic = reader.read(4)

    if tfraMagic != b"tfra":
        typer.echo(
            f"Cannot extract subtitles! Invalid tfra magic in track file {path} (Expected: tfra, Got: {mfraMagic}).",
            err=True,
        )
        return

    version = int.from_bytes(reader.read(1))
    readSize = 8 if version == 1 else 4

    reader.seek(7, os.SEEK_CUR)

    temp = int.from_bytes(reader.read(4))
    lenSizeOfTrafNum = ((temp & 0x3F) >> 4) + 1
    lenSizeOfTrunNum = ((temp & 0xC) >> 2) + 1
    lenSizeOfSampleNum = ((temp & 0x3)) + 1

    numOfEntries = int.from_bytes(reader.read(4))
    fragments = []

    for i in range(numOfEntries):
        _ = int.from_bytes(reader.read(readSize))
        offset = int.from_bytes(reader.read(readSize))
        _ = int.from_bytes(reader.read(lenSizeOfTrafNum))
        _ = int.from_bytes(reader.read(lenSizeOfTrunNum))
        _ = int.from_bytes(reader.read(lenSizeOfSampleNum))

        fragments.append(offset)

    return fragments


def __get_fragment_data(reader, offset):
    reader.seek(offset, os.SEEK_SET)
    moofSize = int.from_bytes(reader.read(4), "big")
    _ = reader.read(moofSize - 4)

    mdatSize = int.from_bytes(reader.read(4), "big")
    mdatBlock = reader.read(mdatSize - 4)

    return mdatBlock[0x4:].decode()


def __get_episode_title(episode_num):
    match episode_num:
        case 1:
            return "EPISODE 1: Monarch Solutions"
        case 2:
            return "EPISODE 2: Prisoner"
        case 3:
            return "EPISODE 3: Deception"
        case 4:
            return "EPISODE 4: The Lifeboat Protocol"
        case _:
            return ""


def __get_text_with_line_breaks(elem):
    lines = []

    for node in elem.iter():
        if node.tag.endswith("br"):
            lines.append("\n")
        elif node.text:
            lines.append(node.text)

    return "".join(lines)


def extract_subtitles(subtitle_path: Path, episode_num: int, track_name: str):
    out = {"episode_title": __get_episode_title(episode_num), "segments": []}
    segments = []

    with open(subtitle_path, "rb") as f:
        offsets = __get_fragment_offsets(f, subtitle_path)

        if not offsets:
            return

        for offset in offsets:
            xml_data = __get_fragment_data(f, offset)

            root = ET.fromstring(xml_data)
            text_segments = root.findall(".//xmlns:p", namespaces=TTML_NS)

            for segment in text_segments:
                segment_id = int(
                    segment.attrib["{http://www.w3.org/XML/1998/namespace}id"].lstrip(
                        "s"
                    )
                )

                if len(segments) > segment_id:
                    segments[segment_id] = __get_text_with_line_breaks(segment)
                else:
                    segments.append(__get_text_with_line_breaks(segment))

    out["segments"] = segments

    with open(
        subtitle_path.parent / f"{track_name}_override.json", "w", encoding="utf-8"
    ) as f:
        json.dump(out, f, indent=4, ensure_ascii=False)

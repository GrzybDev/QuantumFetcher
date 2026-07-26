import os
import xml.etree.ElementTree as ET
from pathlib import Path

from quantumfetcher.constants import TTML_NS
from quantumfetcher.logger import logger


def __get_fragment_offsets(reader, path):
    reader.seek(-4, os.SEEK_END)
    mfroSize = int.from_bytes(reader.read(4))

    reader.seek(-mfroSize, os.SEEK_END)

    mfraBlockSize = int.from_bytes(reader.read(4))

    if mfraBlockSize != mfroSize:
        logger.error(
            f"Cannot extract subtitles! Invalid mfro block size in track file {path} (Expected: {mfroSize}, Got: {mfraBlockSize})."
        )
        return

    mfraMagic = reader.read(4)

    if mfraMagic != b"mfra":
        logger.error(
            f"Cannot extract subtitles! Invalid mfra magic in track file {path} (Expected: mfra, Got: {mfraMagic})."
        )
        return

    reader.seek(4, os.SEEK_CUR)
    tfraMagic = reader.read(4)

    if tfraMagic != b"tfra":
        logger.error(
            f"Cannot extract subtitles! Invalid tfra magic in track file {path} (Expected: tfra, Got: {mfraMagic})."
        )
        return

    version = int.from_bytes(reader.read(1))
    readSize = 8 if version == 1 else 4

    reader.seek(7, os.SEEK_CUR)

    temp = int.from_bytes(reader.read(4))
    lenSizeOfTrafNum = ((temp & 0x3F) >> 4) + 1
    lenSizeOfTrunNum = ((temp & 0xC) >> 2) + 1
    lenSizeOfSampleNum = (temp & 0x3) + 1

    numOfEntries = int.from_bytes(reader.read(4))
    fragments = []

    for _ in range(numOfEntries):
        time = int.from_bytes(reader.read(readSize))
        offset = int.from_bytes(reader.read(readSize))
        _ = int.from_bytes(reader.read(lenSizeOfTrafNum))
        _ = int.from_bytes(reader.read(lenSizeOfTrunNum))
        _ = int.from_bytes(reader.read(lenSizeOfSampleNum))

        fragments.append((time, offset))

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


def __parse_ttml_time(time_str: str) -> float:
    parts = time_str.split(':')
    if len(parts) == 3:
        h, m, s = parts
        sec = int(h) * 3600 + int(m) * 60
        s_parts = s.split('.')
        sec += int(s_parts[0])
        if len(s_parts) > 1:
            sec += float("0." + s_parts[1])
        return sec
    return 0.0


def __format_srt_time(total_sec: float) -> str:
    h = int(total_sec // 3600)
    m = int((total_sec % 3600) // 60)
    s = int(total_sec % 60)
    ms = int(round((total_sec - int(total_sec)) * 1000))
    if ms == 1000:
        s += 1
        ms = 0
        if s == 60:
            m += 1
            s = 0
            if m == 60:
                h += 1
                m = 0
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def extract_subtitles(subtitle_path: Path, episode_num: int, track_name: str, append_ep_title: bool = False):
    segments = []

    with open(subtitle_path, "rb") as f:
        fragments = __get_fragment_offsets(f, subtitle_path)

        if not fragments:
            return

        for tfra_time, offset in fragments:
            frag_time_sec = tfra_time / 10000000.0
            xml_data = __get_fragment_data(f, offset)

            root = ET.fromstring(xml_data)
            text_segments = root.findall(".//xmlns:p", namespaces=TTML_NS)

            for segment in text_segments:
                begin_time = segment.attrib.get("begin", "00:00:00.000")
                end_time = segment.attrib.get("end", "00:00:00.000")
                text = __get_text_with_line_breaks(segment)

                abs_begin = frag_time_sec + __parse_ttml_time(begin_time)
                abs_end = frag_time_sec + __parse_ttml_time(end_time)

                segments.append({
                    "begin": abs_begin,
                    "end": abs_end,
                    "text": text
                })

    if append_ep_title:
        ep_title = __get_episode_title(episode_num)
        if ep_title:
            segments.append({
                "begin": 7.5,
                "end": 9.833,
                "text": ep_title
            })

    segments.sort(key=lambda x: x["begin"])

    merged_segments = []
    for seg in segments:
        if not seg["text"] or not seg["text"].strip():
            continue
        if merged_segments and merged_segments[-1]["text"] == seg["text"]:
            if seg["begin"] - merged_segments[-1]["end"] < 0.1:
                merged_segments[-1]["end"] = max(merged_segments[-1]["end"], seg["end"])
                continue
        merged_segments.append(seg)

    srt_content = []
    srt_index = 1
    for seg in merged_segments:
        srt_content.append(f"{srt_index}")
        srt_content.append(f"{__format_srt_time(seg['begin'])} --> {__format_srt_time(seg['end'])}")
        srt_content.append(seg["text"])
        srt_content.append("")
        srt_index += 1

    with open(
        subtitle_path.parent / f"{track_name}.srt", "w", encoding="utf-8"
    ) as f:
        f.write("\n".join(srt_content))

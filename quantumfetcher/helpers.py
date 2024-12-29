import glob
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path


def __natural_sort_key(s):
    return [
        int(text) if text.isdigit() else text.lower()
        for text in re.split("([0-9]+)", s)
    ]


def extract_subtitles(subtitle_path: Path, subtitle_track_name: str):
    namespaces = {"xmlns": "http://www.w3.org/ns/ttml"}
    subtitle_data = {}

    with open(subtitle_path, "rb") as f:
        f.seek(-4, 2)

        mfra_size = int.from_bytes(f.read(4), "big")
        f.seek(-mfra_size, 2)

        mfra_block_size = int.from_bytes(f.read(4), "big")

        if mfra_size != mfra_block_size:
            raise ValueError(
                "MFRA block size mismatch ({} != {})".format(mfra_size, mfra_block_size)
            )

        mfra_magic = f.read(4)

        if mfra_magic != b"mfra":
            raise ValueError("Invalid MFRA magic: {}".format(mfra_magic))

        tfra_size = int.from_bytes(f.read(4), "big")
        tfra_magic = f.read(4)

        if tfra_magic != b"tfra":
            raise ValueError("Invalid TFRA magic: {}".format(tfra_magic))

        version = int.from_bytes(f.read(1))
        tfra_flags = int.from_bytes(f.read(3))

        track_id = int.from_bytes(f.read(4), "big")

        temp = int.from_bytes(f.read(4), "big")
        length_size_of_traf_num = ((temp & 0x3F) >> 4) + 1
        length_size_of_trun_num = ((temp & 0xC) >> 2) + 1
        length_size_of_sample_num = ((temp & 0x3)) + 1

        number_of_entries = int.from_bytes(f.read(4), "big")

        entries = []

        for _ in range(number_of_entries):
            entry = {}

            if version == 1:
                entry["time"] = int.from_bytes(f.read(8), "big")
                entry["moofOffset"] = int.from_bytes(f.read(8), "big")
            else:
                entry["time"] = int.from_bytes(f.read(4), "big")
                entry["moofOffset"] = int.from_bytes(f.read(4), "big")

            trafNumber = int.from_bytes(f.read(length_size_of_traf_num), "big")
            trunNumber = int.from_bytes(f.read(length_size_of_trun_num), "big")
            sampleNumber = int.from_bytes(f.read(length_size_of_sample_num), "big")

            entries.append(entry)

        for entry in entries:
            f.seek(entry["moofOffset"], 0)

            moof_size = int.from_bytes(f.read(4), "big")
            f.seek(-4, 1)

            moof = f.read(moof_size)

            mdat_size = int.from_bytes(f.read(4), "big")
            f.seek(-4, 1)

            mdat = f.read(mdat_size)

            xml_chunk = mdat[0x8:]
            xml_chunk = re.sub(rb"<br[ ]?[ >/]?>", b"", xml_chunk)  # Remove <br> tags
            root = ET.fromstring(xml_chunk.decode())

            text_segments = root.findall(".//xmlns:p", namespaces=namespaces)

            for segment in text_segments:
                segment_id = segment.attrib["{http://www.w3.org/XML/1998/namespace}id"]
                span = segment.find(".//xmlns:span", namespaces=namespaces)

                subtitle_data[segment_id] = span.text

    subtitle_data_ordered = {
        key: subtitle_data[key] for key in sorted(subtitle_data, key=__natural_sort_key)
    }

    with open(
        subtitle_path.parent / f"{subtitle_track_name}_override.json",
        "w",
        encoding="utf-8",
    ) as f:
        f.write(json.dumps(subtitle_data_ordered, indent=4, ensure_ascii=False))


def update_manifests(episode_path: Path):
    namespaces = {
        "": "http://www.w3.org/2001/SMIL20/Language",
    }

    for key in namespaces:
        ET.register_namespace(key, namespaces[key])

    namespaces["smil"] = namespaces.pop("")

    server_manifest_path = glob.glob(str(episode_path / "*.ism"))[0]

    server_tree = ET.parse(server_manifest_path)
    server_root = server_tree.getroot()

    switch = server_root.find(".//smil:switch", namespaces=namespaces)
    video_streams = server_root.findall(".//smil:video", namespaces=namespaces)
    audio_streams = server_root.findall(".//smil:audio", namespaces=namespaces)
    text_streams = server_root.findall(".//smil:textstream", namespaces=namespaces)

    removed_video_streams = []
    removed_audio_streams = []
    removed_text_streams = []

    for stream in video_streams:
        # Remove video streams if src file does not exist
        if not (episode_path / stream.attrib["src"]).exists():
            removed_video_streams.append(stream.attrib["systemBitrate"])
            switch.remove(stream)

    for stream in audio_streams:
        # Remove audio streams if src file does not exist
        if not (episode_path / stream.attrib["src"]).exists():
            removed_audio_streams.append(
                (stream.attrib["systemLanguage"], stream.attrib["systemBitrate"])
            )
            switch.remove(stream)

    for stream in text_streams:
        # Remove text streams if src file does not exist
        if not (episode_path / stream.attrib["src"]).exists():
            removed_text_streams.append(
                (stream.attrib["systemLanguage"], stream.attrib["systemBitrate"])
            )
            switch.remove(stream)

    server_tree.write(server_manifest_path, encoding="utf-8", xml_declaration=True)

    client_manifest_path = glob.glob(str(episode_path / "*.ismc"))[0]

    client_tree = ET.parse(client_manifest_path)
    client_root = client_tree.getroot()

    streams = client_root.findall(".//StreamIndex")

    for stream in streams:
        quality_levels = stream.findall(".//QualityLevel")
        stream_type = stream.attrib["Type"]

        current_idx = 0

        for level in quality_levels:
            match stream_type:
                case "video":
                    if level.attrib["Bitrate"] in removed_video_streams:
                        stream.remove(level)
                    else:
                        level.attrib["Index"] = str(current_idx)
                        current_idx += 1
                case "audio":
                    if (
                        stream.attrib["Language"],
                        level.attrib["Bitrate"],
                    ) in removed_audio_streams:
                        stream.remove(level)
                    else:
                        level.attrib["Index"] = str(current_idx)
                        current_idx += 1
                case "text":
                    if (
                        stream.attrib["Language"],
                        level.attrib["Bitrate"],
                    ) in removed_text_streams:
                        stream.remove(level)
                    else:
                        level.attrib["Index"] = str(current_idx)
                        current_idx += 1

        if current_idx == 0:
            client_root.remove(stream)

    client_tree.write(client_manifest_path, encoding="utf-8", xml_declaration=True)

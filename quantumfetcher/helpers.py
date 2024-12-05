import glob
import json
import re
import xml.etree.ElementTree as ET
from io import StringIO


def __natural_sort_key(s):
    return [
        int(text) if text.isdigit() else text.lower()
        for text in re.split("([0-9]+)", s)
    ]


def extract_subtitles(video_path, subtitle_track_name):
    subtitle_data = {}

    for subtitle_file in glob.glob(f"{video_path}/{subtitle_track_name}/*.ismt"):
        subtitle_chunk = None

        with open(subtitle_file, "rb") as f:
            subtitle_chunk = f.read()

        xml_chunk = subtitle_chunk[0x58:]  # Skip the mp4 chunk header

        root = ET.fromstring(xml_chunk)
        namespaces = dict(
            [
                node
                for _, node in ET.iterparse(
                    StringIO(xml_chunk.decode()), events=["start-ns"]
                )
            ],
            xml="http://www.w3.org/XML/1998/namespace",
        )

        body = root.find("body", namespaces)
        div = body.find("div", namespaces)

        for p in div.findall("p", namespaces):
            segment_id = p.attrib["{" + namespaces["xml"] + "}id"]

            for span in p.findall("span", namespaces):
                if span.text:
                    subtitle_data[segment_id] = span.text

    subtitle_data_ordered = {
        key: subtitle_data[key] for key in sorted(subtitle_data, key=__natural_sort_key)
    }

    with open(
        f"{video_path}/{subtitle_track_name}_override.json", "w", encoding="utf-8"
    ) as f:
        json.dump(subtitle_data_ordered, f, indent=4, ensure_ascii=False)

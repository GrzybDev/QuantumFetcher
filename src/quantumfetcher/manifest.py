import xml.etree.ElementTree as ET
from pathlib import Path
import requests

from quantumfetcher.constants import SMIL_NS, USER_AGENT
from quantumfetcher.enumerators.language import LanguageMap
from quantumfetcher.logger import logger


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

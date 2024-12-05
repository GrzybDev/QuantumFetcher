import json
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
import typer
from tqdm import tqdm

from quantumfetcher import helpers

app = typer.Typer()

RMDJ_KEY = [
    0xBA,
    0x7A,
    0xBB,
    0x27,
    0x03,
    0x9B,
    0x72,
    0xFD,
    0x13,
    0xEB,
    0x70,
    0x38,
    0x7E,
    0x0F,
    0xCB,
    0x41,
    0xE1,
    0xD0,
    0xEB,
    0x54,
    0xBE,
    0x8F,
    0x13,
    0x6D,
    0xF0,
    0xBA,
    0xE2,
    0x2A,
    0xDC,
    0xFB,
    0x40,
    0xF1,
]


@app.command()
def main(
    path: Path = typer.Argument(help="Path to the game folder"),
    episode: str = typer.Option(None, help="If set, only fetch this episode"),
    max_resolution: int = typer.Option(
        None, help="If set, maximum video resolution to fetch"
    ),
    max_bitrate: int = typer.Option(
        None, help="If set, maximum video bitrate to fetch"
    ),
    audio_languages: str = typer.Option(
        "eng", help="Comma-separated list of audio languages to fetch"
    ),
    subtitle_languages: str = typer.Option(
        "eng", help="Comma-separated list of subtitle languages to fetch"
    ),
    extract_subtitles: bool = typer.Option(
        False, help="Extract subtitles to .json after fetching"
    ),
):
    if audio_languages:
        audio_languages = audio_languages.split(",")

    if subtitle_languages:
        subtitle_languages = subtitle_languages.split(",")

    if not path.is_dir():
        raise typer.BadParameter(f"Path {path} is not a directory")

    video_list_path = path / "data/videoList.rmdj"

    if not video_list_path.exists():
        raise typer.BadParameter(
            f"Path {path} does not contain a data/videoList.rmdj file"
        )

    if (path / "data/videoList_original.rmdj").is_file():
        video_list_path = path / "data/videoList_original.rmdj"

    decrypted_video_list = []
    with open(video_list_path, "rb") as f:
        video_list_bytes = f.read()

        for byte in video_list_bytes:
            decrypted_video_list.append(byte ^ RMDJ_KEY[len(decrypted_video_list) % 32])

    try:
        video_list = json.loads("".join([chr(byte) for byte in decrypted_video_list]))
    except json.JSONDecodeError:
        raise typer.BadParameter(f"Failed to decode video list")

    if episode is not None:
        if episode not in video_list:
            raise typer.BadParameter(f"Episode {episode} not found in video list")

        video_list = {episode: video_list[episode]}

    pbar_episodes = tqdm(
        video_list, desc="episode", position=0, leave=False, unit="episode"
    )
    for episode in pbar_episodes:
        pbar_episodes.set_description(episode)

        episodepath = path / "videos" / "episodes" / episode
        episodeurl = video_list[episode]

        episodepath.mkdir(parents=True, exist_ok=True)

        manifestpath = episodepath / "manifest.ismc"
        manifestdata = None

        if not manifestpath.exists():
            try:
                req_manifest = requests.get(episodeurl)
                req_manifest.raise_for_status()
            except requests.exceptions.RequestException as e:
                typer.echo(f"Failed to fetch manifest for {episode}: {e}, Skipping...")
                continue

            with open(manifestpath, "wb") as f:
                f.write(req_manifest.content)
                manifestdata = req_manifest.content
        else:
            with open(manifestpath, "rb") as f:
                manifestdata = f.read()

        if not manifestdata:
            typer.echo(f"Failed to read manifest for {episode}, Skipping...")
            continue

        manifestdata = manifestdata.decode("utf-8")
        manifest = ET.fromstring(manifestdata)

        fragment_base_url = episodeurl.split("manifest")[0]
        streams = {}

        for child in manifest:
            quality_levels_data = []
            chunks_data = []

            type = child.attrib["Type"]
            lang = child.attrib.get("Language", None)
            name = child.attrib.get("Name", None)
            child.attrib["QualityLevels"] = "1"
            url = child.attrib["Url"].replace("start time", "starttime")

            for subchild in child:
                if "QualityLevel" in subchild.tag:
                    quality_levels_data.append(subchild)
                elif "c" in subchild.tag:
                    chunks_data.append(int(subchild.attrib["d"]))

            selected_bitrate = 0
            for subchild in quality_levels_data:
                if type == "video":
                    if (
                        max_resolution is not None
                        and int(subchild.attrib["MaxHeight"]) > max_resolution
                    ):
                        continue

                    if (
                        max_bitrate is not None
                        and int(subchild.attrib["Bitrate"]) > max_bitrate
                    ):
                        continue

                selected_bitrate = max(
                    selected_bitrate, int(subchild.attrib["Bitrate"])
                )

            if selected_bitrate == 0:
                typer.echo(
                    f"No suitable quality level found for {episode}, Skipping..."
                )
                break

            for subchild in quality_levels_data:
                if int(subchild.attrib["Bitrate"]) != selected_bitrate:
                    child.remove(subchild)
                else:
                    subchild.attrib["Index"] = "0"

            # Save the manifest with the selected quality level
            with open(manifestpath, "w") as f:
                f.write(ET.tostring(manifest).decode("utf-8"))

            stream_folder = type if name is None else name

            if type == "audio" and audio_languages:
                if lang not in audio_languages:
                    continue
            elif type == "text" and subtitle_languages:
                if lang not in subtitle_languages:
                    continue

            stream_path = episodepath / stream_folder
            stream_path.mkdir(parents=True, exist_ok=True)

            streams[stream_folder] = {
                "fragment_url": url,
                "type": type[:1],
                "stream_folder": stream_folder,
                "selected_bitrate": selected_bitrate,
                "chunks_data": chunks_data,
            }

        pbar_stream = tqdm(
            streams, desc="stream", position=1, leave=False, unit="stream"
        )
        for stream in pbar_stream:
            pbar_stream.set_description(stream)

            current_offset = 0
            target_folder = streams[stream]["stream_folder"]
            stream_type = streams[stream]["type"]

            pbar_chunk = tqdm(
                streams[stream]["chunks_data"], position=2, leave=False, unit="chunk"
            )
            for chunk in pbar_chunk:
                chunk_url = fragment_base_url
                chunk_url += streams[stream]["fragment_url"].format(
                    bitrate=streams[stream]["selected_bitrate"],
                    starttime=current_offset,
                )

                chunk_path = (
                    episodepath
                    / target_folder
                    / (f"{current_offset}.ism" + stream_type)
                )

                if not chunk_path.exists():
                    while True:
                        try:
                            req_chunk = requests.get(chunk_url)
                            req_chunk.raise_for_status()
                            break
                        except requests.exceptions.RequestException as e:
                            typer.echo(
                                f"Failed to fetch chunk {current_offset} for {episode}, retrying..."
                            )
                            continue

                    with open(chunk_path, "wb") as f:
                        f.write(req_chunk.content)

                current_offset += chunk

            if extract_subtitles and stream_type == "t":
                helpers.extract_subtitles(episodepath, target_folder)


if __name__ == "__main__":
    app()

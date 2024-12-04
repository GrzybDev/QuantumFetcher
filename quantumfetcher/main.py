from pathlib import Path
import typer
import json
from tqdm import tqdm
import requests
import xml.etree.ElementTree as ET

app = typer.Typer()

RMDJ_KEY = [0xba, 0x7a, 0xbb, 0x27, 0x03, 0x9b, 0x72, 0xfd, 0x13, 0xeb, 0x70, 0x38, 0x7e, 0x0f, 0xcb, 0x41, 0xe1, 0xd0, 0xeb, 0x54, 0xbe, 0x8f, 0x13, 0x6d, 0xf0, 0xba, 0xe2, 0x2a, 0xdc, 0xfb, 0x40, 0xf1]

@app.command()
def main(path: Path = typer.Argument(help="Path to the game folder")):
    if not path.is_dir():
        raise typer.BadParameter(f"Path {path} is not a directory")
    
    video_list_path = path / "data/videoList.rmdj"
    
    if not video_list_path.exists():
        raise typer.BadParameter(f"Path {path} does not contain a data/videoList.rmdj file")
    
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
    
    pbar_episodes = tqdm(video_list, desc="episode", position=0, leave=False, unit=" episode")
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
            quality_levels = []
            quality_levels_data = []
            chunks_data = []

            type = child.attrib["Type"]
            name = child.attrib.get("Name", None)
            child.attrib["QualityLevels"] = "1"
            url = child.attrib["Url"].replace("start time", "starttime")

            for subchild in child:
                if "QualityLevel" in subchild.tag:
                    quality_levels.append(int(subchild.attrib["Bitrate"]))
                    quality_levels_data.append(subchild)
                elif "c" in subchild.tag:
                    chunks_data.append(int(subchild.attrib["d"]))

            selected_bitrate = max(quality_levels)

            for subchild in quality_levels_data:
                if int(subchild.attrib["Bitrate"]) != selected_bitrate:
                    child.remove(subchild)
                else:
                    subchild.attrib["Index"] = "0"

            # Save the manifest with the selected quality level
            with open(manifestpath, "w") as f:
                f.write(ET.tostring(manifest).decode("utf-8"))

            stream_folder = type if name is None else name

            stream_path = episodepath / stream_folder
            stream_path.mkdir(parents=True, exist_ok=True)

            type = None
            if stream_folder == "video":
                type = "v"
            elif "_captions" in stream_folder:
                type = "t"
            else:
                type = "a"

            streams[stream_folder] = {
                "fragment_url": url,
                "type": type,
                "stream_folder": stream_folder,
                "quality_levels": quality_levels,
                "chunks_data": chunks_data,
            }
        
        pbar_stream = tqdm(streams, desc="stream", position=1, leave=False, unit=" stream")
        for stream in pbar_stream:
            pbar_stream.set_description(stream)

            current_offset = 0
            target_folder = streams[stream]["stream_folder"]
            stream_type = streams[stream]["type"]
            
            pbar_chunk = tqdm(streams[stream]["chunks_data"], desc="chunk", position=2, leave=False, unit=" chunk")
            for chunk in pbar_chunk:
                chunk_url = fragment_base_url
                chunk_url += streams[stream]["fragment_url"].format(
                    bitrate=max(streams[stream]["quality_levels"]), starttime=current_offset
                )

                chunk_path = episodepath / target_folder / (f"{current_offset}.ism" + stream_type)

                if not chunk_path.exists():
                    try:
                        req_chunk = requests.get(chunk_url)
                        req_chunk.raise_for_status()
                    except requests.exceptions.RequestException as e:
                        typer.echo(f"Failed to fetch chunk {current_offset} for {episode}, Skipping...")
                        continue

                    with open(chunk_path, "wb") as f:
                        f.write(req_chunk.content)
                
                current_offset += chunk

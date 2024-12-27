import sys
import xml.etree.ElementTree as ET

import requests

from quantumfetcher.helpers import extract_subtitles
from quantumfetcher.stream import Stream


class Smooth:

    buffer_size = 1024  # 1KB
    chunk_size = 1024 * 1024 * 10  # 10MB
    namespace = {"smil": "http://www.w3.org/2001/SMIL20/Language"}

    def __init__(self, ism: bytes, base_url: str):
        self.__video_streams = []
        self.__audio_streams = []
        self.__text_streams = []

        self.ism = ET.fromstring(ism.decode("utf-8"))
        self.base_url = base_url

        self.__get_streams()

    def __get_streams(self):
        video_streams = self.ism.findall(".//smil:video", namespaces=self.namespace)
        audio_streams = self.ism.findall(".//smil:audio", namespaces=self.namespace)
        text_streams = self.ism.findall(".//smil:textstream", namespaces=self.namespace)

        for stream in video_streams:
            self.__video_streams.append(
                Stream(
                    filename=stream.attrib["src"],
                    bitrate=int(stream.attrib["systemBitrate"]),
                )
            )

        for stream in audio_streams:
            self.__audio_streams.append(
                Stream(
                    filename=stream.attrib["src"],
                    bitrate=int(stream.attrib["systemBitrate"]),
                    language=stream.attrib.get("systemLanguage"),
                )
            )

        for stream in text_streams:
            track_name = stream.find(
                ".//smil:param[@name='trackName']", namespaces=self.namespace
            )

            self.__text_streams.append(
                Stream(
                    filename=stream.attrib["src"],
                    bitrate=int(stream.attrib["systemBitrate"]),
                    language=stream.attrib.get("systemLanguage"),
                    trackName=track_name.attrib.get("value"),
                )
            )

    def get_available_video_bitrates(self) -> list[int]:
        return [stream.bitrate for stream in self.__video_streams]

    def get_highest_video_bitrate(self, maxBitrate: int) -> int:
        if maxBitrate is None:
            return max(self.get_available_video_bitrates())

        return max(
            [
                bitrate
                for bitrate in self.get_available_video_bitrates()
                if bitrate <= maxBitrate
            ]
        )

    def get_available_audio_bitrates(self) -> list[int]:
        # Return the audio bitrates per language

        # Get the unique languages
        languages = set([stream.language for stream in self.__audio_streams])

        # Get the bitrates per language
        return {
            language: [
                stream.bitrate
                for stream in self.__audio_streams
                if stream.language == stream.language
            ]
            for language in languages
        }

    def get_available_audio_languages(self) -> list[str]:
        return [stream.language for stream in self.__audio_streams]

    def get_highest_audio_bitrate(self, language: str, maxBitrate: int) -> int:
        if maxBitrate is None:
            return max(
                [
                    stream.bitrate
                    for stream in self.__audio_streams
                    if stream.language == language
                ]
            )

        return max(
            [
                stream.bitrate
                for stream in self.__audio_streams
                if stream.language == language and stream.bitrate <= maxBitrate
            ]
        )

    def get_available_text_languages(self) -> list[str]:
        return [stream.language for stream in self.__text_streams]

    def get_client_manifest_relative_path(self) -> str:
        return self.ism.find(
            ".//smil:meta[@name='clientManifestRelativePath']",
            namespaces=self.namespace,
        ).attrib["content"]

    def download_video(self, bitrate, path, progress):
        video_stream = next(
            stream for stream in self.__video_streams if stream.bitrate == bitrate
        )

        return self.download(video_stream, "video", path, progress)

    def download_audio(self, language, bitrate, path, progress):
        audio_stream = next(
            stream
            for stream in self.__audio_streams
            if stream.language == language and stream.bitrate == bitrate
        )

        return self.download(audio_stream, "audio", path, progress)

    def download_text(self, language, path, generate_subtitles, progress):
        text_stream = next(
            stream for stream in self.__text_streams if stream.language == language
        )

        dl_task = self.download(text_stream, "text", path, progress)
        stream_path = path / text_stream.filename

        if generate_subtitles:
            extract_subtitles(stream_path, text_stream.trackName)

        return dl_task

    def download(self, stream, stream_type, path, progress):
        stream_url = f"{self.base_url}/{stream.filename}"
        stream_path = path / stream.filename

        if stream_path.exists():
            # Check if the file is fully downloaded
            with requests.head(stream_url) as r:
                content_length = int(r.headers["Content-Length"])

            start_range = stream_path.stat().st_size
        else:
            start_range = 0
            content_length = None

        return self.__stream_download(
            stream_url, stream_path, progress, stream_type, start_range, content_length
        )

    def __stream_download(
        self, url, path, progress, stream_type, start_range=0, content_length=None
    ):
        current_range = start_range

        if content_length is None:
            with requests.head(url) as r:
                content_length = int(r.headers["Content-Length"])

        dl_task = progress.add_task(
            f"Downloading {stream_type} stream ({path.name})...", total=content_length
        )
        progress.update(dl_task, advance=start_range)

        with open(path, "ab") as f:
            while current_range < content_length:
                end_range = min(current_range + self.chunk_size, content_length) - 1
                headers = {"X-MS-Range": f"bytes={current_range}-{end_range}"}

                with requests.get(url, headers=headers, stream=True) as r:
                    r.raise_for_status()

                    for chunk in r.iter_content(chunk_size=self.buffer_size):
                        f.write(chunk)
                        current_range += len(chunk)
                        progress.update(dl_task, advance=len(chunk))

        return dl_task

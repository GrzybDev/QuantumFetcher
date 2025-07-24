import xml.etree.ElementTree as ET

from quantumfetcher.dataclasses.stream import ClientStream
from quantumfetcher.dataclasses.stream_audio import AudioStream
from quantumfetcher.dataclasses.stream_text import TextStream
from quantumfetcher.dataclasses.stream_video import VideoStream
from quantumfetcher.enumerators.language import Language
from quantumfetcher.enumerators.type_stream import StreamType
from quantumfetcher.manifests.base import BaseManifest


class ClientManifest(BaseManifest):

    __headers: dict[str, str]
    __streams: list[ClientStream]

    def __init__(self, content: str) -> None:
        tree = ET.ElementTree(ET.fromstring(content))
        root = tree.getroot()

        # Extract headers attributes
        self.__headers = root.attrib  # type: ignore

        self.__parse_stream_indexes(root)

    def __parse_stream_indexes(self, root):
        self.__streams = []

        for stream in root.findall("StreamIndex"):
            qualityLevels = []
            chunks = []

            for ql in stream.findall("QualityLevel"):
                qualityLevels.append(ql.attrib)

            for chunk in stream.findall("c"):
                if "n" in chunk.attrib and "d" in chunk.attrib:
                    # If 'n' is present, override the chunk number
                    chunk_number = int(chunk.attrib["n"])

                    if chunk_number != len(chunks):
                        raise ValueError(
                            f"Chunk number mismatch: expected {len(chunks)}, got {chunk_number}"
                        )

                    # Convert to int and add to qualityLevels
                    chunks.append(int(chunk.attrib["d"]))

            self.__streams.append(
                ClientStream(
                    type=StreamType(stream.attrib.get("Type")),
                    attributes=stream.attrib,
                    qualityLevels=qualityLevels,
                    chunks=chunks,
                )
            )

    def list_video_streams(self):
        streams = []

        for stream in self.__streams:
            if stream.attributes.get("Type") != "video":
                continue

            for ql in stream.qualityLevels:
                streams.append(
                    VideoStream(
                        width=int(ql.get("MaxWidth", -1)),
                        height=int(ql.get("MaxHeight", -1)),
                        bitrate=int(ql.get("Bitrate", -1)),
                        codec=ql.get("FourCC", ""),
                    )
                )

        return streams

    def list_audio_streams(self):
        streams = []

        for stream in self.__streams:
            if stream.attributes.get("Type") != "audio":
                continue

            for ql in stream.qualityLevels:
                streams.append(
                    AudioStream(
                        name=stream.attributes.get("Name", ""),
                        language=Language(stream.attributes.get("Language", "unk")),
                        bitrate=int(ql.get("Bitrate", -1)),
                        samplingRate=int(ql.get("SamplingRate", -1)),
                        channels=int(ql.get("Channels", -1)),
                        bitsPerSample=int(ql.get("BitsPerSample", -1)),
                        codec=ql.get("FourCC", ""),
                    )
                )

        return streams

    def list_text_streams(self):
        streams = []

        for stream in self.__streams:
            if stream.attributes.get("Type") != "text":
                continue

            for ql in stream.qualityLevels:
                streams.append(
                    TextStream(
                        name=stream.attributes.get("Name", ""),
                        language=Language(stream.attributes.get("Language", "unk")),
                        bitrate=int(ql.get("Bitrate", -1)),
                        codec=ql.get("FourCC", ""),
                    )
                )

        return streams

    def list_streams(self, mediaType: StreamType):
        match mediaType:
            case StreamType.Video:
                return self.list_video_streams()
            case StreamType.Audio:
                return self.list_audio_streams()
            case StreamType.Text:
                return self.list_text_streams()

    def get_chunks_count(self, mediaType: StreamType, trackName=None):
        for stream in self.__streams:
            if (
                stream.attributes.get("Type") != mediaType.value
                if mediaType != StreamType.Text
                else "text"
            ):
                continue

            if trackName and stream.attributes.get("Name") != trackName:
                continue

            return int(stream.attributes.get("Chunks"))  # type: ignore
        else:
            return -1

    def save(self, path, streams) -> None:
        root = ET.Element("SmoothStreamingMedia", attrib=self.__headers)

        video_bitrates = {s.bitrate for s in streams if isinstance(s, VideoStream)}
        named_streams = {
            (
                StreamType.Audio if isinstance(s, AudioStream) else StreamType.Text,
                s.name,
                s.language.value,
            )
            for s in streams
            if not isinstance(s, VideoStream)
        }

        def add_video_stream(stream):
            stream_index = ET.SubElement(root, "StreamIndex", attrib=stream.attributes)
            max_width = max_height = ql_idx = 0
            for ql in stream.qualityLevels:
                if int(ql.get("Bitrate", -1)) in video_bitrates:
                    max_width = max(max_width, int(ql.get("MaxWidth", 0)))
                    max_height = max(max_height, int(ql.get("MaxHeight", 0)))
                    ql["Index"] = str(ql_idx)
                    ql_idx += 1
                    quality_level = ET.SubElement(
                        stream_index, "QualityLevel", attrib=ql
                    )
                    quality_level.set("Bitrate", str(ql.get("Bitrate", -1)))
            for idx, chunk in enumerate(stream.chunks):
                ET.SubElement(stream_index, "c", n=str(idx), d=str(chunk))
            stream_index.attrib.update(
                {
                    "QualityLevels": str(ql_idx),
                    "MaxWidth": str(max_width),
                    "MaxHeight": str(max_height),
                    "DisplayWidth": str(max_width),
                    "DisplayHeight": str(max_height),
                }
            )

        def add_named_stream(stream):
            key = (
                stream.type,
                stream.attributes.get("Name"),
                stream.attributes.get("Language"),
            )
            if key not in named_streams:
                return
            stream_index = ET.SubElement(root, "StreamIndex", attrib=stream.attributes)
            for ql in stream.qualityLevels:
                ET.SubElement(stream_index, "QualityLevel", attrib=ql)
            for idx, chunk in enumerate(stream.chunks):
                ET.SubElement(stream_index, "c", n=str(idx), d=str(chunk))

        for stream in self.__streams:
            if stream.type == StreamType.Video:
                add_video_stream(stream)
            elif stream.type in (StreamType.Audio, StreamType.Text):
                add_named_stream(stream)

        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ", level=0)
        tree.write(path, xml_declaration=True, encoding="UTF-8")

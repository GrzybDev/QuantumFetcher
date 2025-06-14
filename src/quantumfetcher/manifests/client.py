import xml.etree.ElementTree as ET
from xml.dom import minidom

from quantumfetcher.dataclasses.SmoothStreamingMedia import SmoothStreamingMedia
from quantumfetcher.enumerators.Language import Language
from quantumfetcher.enumerators.StreamType import StreamType


class ClientManifest:

    __headers: dict[str, str]
    __streams: list[SmoothStreamingMedia]

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
                SmoothStreamingMedia(
                    attributes=stream.attrib, qualityLevels=qualityLevels, chunks=chunks
                )
            )

    def save(self, path):
        ssm = ET.Element("SmoothStreamingMedia", attrib=self.__headers)

        for stream in self.__streams:
            stream_el = ET.SubElement(ssm, "StreamIndex", attrib=stream.attributes)

            for ql in stream.qualityLevels:
                ET.SubElement(stream_el, "QualityLevel", attrib=ql)

            for idx, chunk in enumerate(stream.chunks):
                chunk_el = ET.SubElement(stream_el, "c")
                chunk_el.set("n", str(idx))
                chunk_el.set("d", str(chunk))

        finalxml = ET.tostring(ssm, encoding="unicode", xml_declaration=True)

        with open(path, "w", encoding="utf-8") as f:
            parsed = minidom.parseString(finalxml)
            f.write(parsed.toprettyxml(indent="  "))

    def list_video_streams(self):
        streams = []

        for stream in self.__streams:
            if stream.attributes.get("Type") != "video":
                continue

            for ql in stream.qualityLevels:
                streams.append(
                    (
                        int(ql.get("MaxWidth", -1)),
                        int(ql.get("MaxHeight", -1)),
                        int(ql.get("Bitrate", -1)),
                        ql.get("FourCC", ""),
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
                    (
                        stream.attributes.get("Name", ""),
                        Language(stream.attributes.get("Language", "unk")),
                        int(ql.get("Bitrate", -1)),
                        int(ql.get("SamplingRate", -1)),
                        int(ql.get("Channels", -1)),
                        int(ql.get("BitsPerSample", -1)),
                        ql.get("FourCC", ""),
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
                    (
                        stream.attributes.get("Name", ""),
                        Language(stream.attributes.get("Language", "unk")),
                        int(ql.get("Bitrate", -1)),
                        ql.get("FourCC", ""),
                    )
                )

        return streams

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

            return int(stream.attributes.get("Chunks"))
        else:
            return -1

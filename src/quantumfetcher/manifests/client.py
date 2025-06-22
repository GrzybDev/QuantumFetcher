import xml.etree.ElementTree as ET

from quantumfetcher.dataclasses.stream import ClientStream
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

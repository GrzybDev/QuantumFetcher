import xml.etree.ElementTree as ET
from xml.dom import minidom

from quantumfetcher.dataclasses.SmoothStreamingMedia import SmoothStreamingMedia


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

            for ql in stream.findall("QualityLevel"):
                qualityLevels.append(ql.attrib)

            self.__streams.append(
                SmoothStreamingMedia(
                    attributes=stream.attrib, qualityLevels=qualityLevels
                )
            )

    def save(self, path):
        ssm = ET.Element("SmoothStreamingMedia", attrib=self.__headers)

        for stream in self.__streams:
            stream_el = ET.SubElement(ssm, "StreamIndex", attrib=stream.attributes)

            for ql in stream.qualityLevels:
                ET.SubElement(stream_el, "QualityLevel", attrib=ql)

        finalxml = ET.tostring(ssm, encoding="unicode", xml_declaration=True)

        with open(path, "w", encoding="utf-8") as f:
            parsed = minidom.parseString(finalxml)
            f.write(parsed.toprettyxml(indent="  "))

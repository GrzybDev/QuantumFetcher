import xml.etree.ElementTree as ET
from xml.dom import minidom

from quantumfetcher.constants import XML_NS
from quantumfetcher.dataclasses.SmoothStream import SmoothStream
from quantumfetcher.enumerators.StreamType import StreamType


class ServerManifest:

    __headers: dict[str, str]
    __streams: list[SmoothStream]

    def __init__(self, content: str) -> None:
        tree = ET.ElementTree(ET.fromstring(content))
        root = tree.getroot()

        self.__parse_headers(root)
        self.__parse_media_streams(root)

    def __parse_headers(self, root):
        self.__headers = {}

        for meta in root.find("smil:head", XML_NS).findall("smil:meta", XML_NS):
            name = meta.attrib.get("name")
            content = meta.attrib.get("content")

            if name and content:
                self.__headers[name] = content

    def __parse_media_streams(self, root):
        self.__streams = []
        switch = root.find("smil:body/smil:switch", XML_NS)

        if switch is not None:
            for stream in switch:
                stream_type_str = stream.tag.split("}")[1]
                attributes = stream.attrib
                params = {}

                for param in stream.findall("smil:param", XML_NS):
                    name = param.attrib.get("name")
                    value = param.attrib.get("value")
                    if name and value:
                        params[name] = value

                self.__streams.append(
                    SmoothStream(
                        type=StreamType(stream_type_str),
                        attributes=attributes,
                        parameters=params,
                    )
                )

    def save(self, path):
        ET.register_namespace("", "http://www.w3.org/2001/SMIL20/Language")
        smil_ns = "http://www.w3.org/2001/SMIL20/Language"
        smil = ET.Element(f"{{{smil_ns}}}smil")

        # Head
        head = ET.SubElement(smil, f"{{{smil_ns}}}head")
        for key, value in self.__headers.items():
            ET.SubElement(head, f"{{{smil_ns}}}meta", name=key, content=value)

        # Body -> Switch
        body = ET.SubElement(smil, f"{{{smil_ns}}}body")
        switch = ET.SubElement(body, f"{{{smil_ns}}}switch")

        for stream in self.__streams:
            stream_el = ET.SubElement(
                switch, f"{{{smil_ns}}}{stream.type.value}", attrib=stream.attributes
            )
            for pname, pvalue in stream.parameters.items():
                ET.SubElement(
                    stream_el,
                    f"{{{smil_ns}}}param",
                    name=pname,
                    value=pvalue,
                    valuetype="data",
                )

        finalxml = ET.tostring(smil, encoding="unicode", xml_declaration=True)

        with open(path, "w", encoding="utf-8") as f:
            parsed = minidom.parseString(finalxml)
            f.write(parsed.toprettyxml(indent="  "))

    def __get_all_bitrates(self, type, trackName=None):
        output = []

        for stream in self.__streams:
            if stream.type != type:
                continue

            if trackName and stream.parameters.get("trackName") != trackName:
                continue

            output.append(int(stream.attributes.get("systemBitrate", -1)))

        return output

    def __get_stream(self, type, bitrate, trackName=None):
        for stream in self.__streams:
            if stream.type != type:
                continue

            if trackName and stream.parameters.get("trackName") != trackName:
                continue

            if int(stream.attributes.get("systemBitrate", -1)) == bitrate:
                return stream

    def __get_closest_lte(self, vals, target):
        filtered = [n for n in vals if n <= target]
        return max(filtered) if filtered else None

    def get_video_stream(self, bitrate):
        bitrates = self.__get_all_bitrates(StreamType.Video)
        closest_match = self.__get_closest_lte(bitrates, bitrate)
        return self.__get_stream(StreamType.Video, closest_match)

    def get_named_stream(self, name, type, bitrate):
        bitrates = self.__get_all_bitrates(type, trackName=name)
        closest_match = self.__get_closest_lte(bitrates, bitrate)
        return self.__get_stream(type, closest_match, trackName=name)

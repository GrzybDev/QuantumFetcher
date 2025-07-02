import xml.etree.ElementTree as ET

from quantumfetcher.constants import XML_NS
from quantumfetcher.dataclasses.stream import ServerStream
from quantumfetcher.enumerators.type_stream import StreamType
from quantumfetcher.manifests.base import BaseManifest


class ServerManifest(BaseManifest):

    __headers: dict[str, str]
    __streams: list[ServerStream]

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
                stream_type_str = stream.tag.split("}")[1].replace("stream", "")

                attributes = stream.attrib
                params = {}

                for param in stream.findall("smil:param", XML_NS):
                    name = param.attrib.get("name")
                    value = param.attrib.get("value")
                    if name and value:
                        params[name] = value

                self.__streams.append(
                    ServerStream(
                        type=StreamType(stream_type_str),
                        attributes=attributes,
                        parameters=params,
                    )
                )

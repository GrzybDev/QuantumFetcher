import xml.etree.ElementTree as ET

from quantumfetcher.constants import SMIL_NS
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

        for meta in root.find("smil:head", SMIL_NS).findall("smil:meta", SMIL_NS):
            name = meta.attrib.get("name")
            content = meta.attrib.get("content")

            if name and content:
                self.__headers[name] = content

    def __parse_media_streams(self, root):
        self.__streams = []
        switch = root.find("smil:body/smil:switch", SMIL_NS)

        if switch is not None:
            for stream in switch:
                stream_type_str = stream.tag.split("}")[1].replace("stream", "")

                attributes = stream.attrib
                params = {}

                for param in stream.findall("smil:param", SMIL_NS):
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

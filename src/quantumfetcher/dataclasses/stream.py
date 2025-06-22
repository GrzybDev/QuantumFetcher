from dataclasses import dataclass

from quantumfetcher.enumerators.type_stream import StreamType


@dataclass
class StreamBase:
    attributes: dict[str, str]
    type: StreamType


@dataclass
class ClientStream(StreamBase):
    qualityLevels: list[dict[str, str]]
    chunks: list[int]


@dataclass
class ServerStream(StreamBase):
    parameters: dict[str, str]

from dataclasses import dataclass

from quantumfetcher.enumerators.stream_type import StreamType


@dataclass
class SmoothStream:
    type: StreamType
    attributes: dict[str, str]
    parameters: dict[str, str]

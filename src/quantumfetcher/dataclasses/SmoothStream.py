from dataclasses import dataclass

from quantumfetcher.enumerators.StreamType import StreamType


@dataclass
class SmoothStream:
    type: StreamType
    attributes: dict[str, str]
    parameters: dict[str, str]

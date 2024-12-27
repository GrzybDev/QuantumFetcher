from dataclasses import dataclass
from typing import Optional


@dataclass
class Stream:
    filename: str
    bitrate: int
    language: Optional[str] = None
    trackName: Optional[str] = None

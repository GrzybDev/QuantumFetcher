from dataclasses import dataclass


@dataclass
class VideoStream:
    width: int
    height: int
    bitrate: int
    format: str

    def __str__(self) -> str:
        return f"{self.height}p ({self.format} - {self.width}x{self.height} @ {self.bitrate} bps)"

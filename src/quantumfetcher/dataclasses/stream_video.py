from dataclasses import dataclass


@dataclass(frozen=True)
class VideoStream:
    width: int
    height: int
    bitrate: int
    codec: str

    def __str__(self) -> str:
        return f"{self.height}p ({self.codec} - {self.width}x{self.height} @ {self.bitrate} bps)"

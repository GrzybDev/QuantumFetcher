from dataclasses import dataclass

from quantumfetcher.enumerators.Language import Language


@dataclass
class TextStream:
    name: str
    language: Language
    bitrate: int
    format: str

    def __str__(self) -> str:
        return (
            f"{self.language.name} ({self.format} - {self.name} @ {self.bitrate} bps)"
        )

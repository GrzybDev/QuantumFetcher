from dataclasses import dataclass

from quantumfetcher.enumerators.language import Language


@dataclass(frozen=True)
class TextStream:
    name: str
    language: Language
    bitrate: int
    codec: str

    def __str__(self) -> str:
        return f"{self.language.name} ({self.codec} - {self.name} @ {self.bitrate} bps)"

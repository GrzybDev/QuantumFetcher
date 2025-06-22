from dataclasses import dataclass

from quantumfetcher.enumerators.language import Language


@dataclass(frozen=True)
class AudioStream:
    name: str
    language: Language
    bitrate: int
    samplingRate: int
    channels: int
    bitsPerSample: int
    codec: str

    def __str__(self) -> str:
        return f"{self.language.name} ({self.codec} - {self.samplingRate}hz, {self.bitsPerSample}-bit, {self.channels} channels @ {self.bitrate} bps)"

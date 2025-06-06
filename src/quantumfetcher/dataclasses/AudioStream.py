from dataclasses import dataclass

from quantumfetcher.enumerators.Language import Language


@dataclass
class AudioStream:
    name: str
    language: Language
    bitrate: int
    samplingRate: int
    channels: int
    bitsPerSample: int
    format: str

    def __str__(self) -> str:
        return f"{self.language.name} ({self.format} - {self.samplingRate}hz, {self.bitsPerSample}-bit, {self.channels} channels @ {self.bitrate} bps)"

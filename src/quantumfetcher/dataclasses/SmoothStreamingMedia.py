from dataclasses import dataclass


@dataclass
class SmoothStreamingMedia:
    attributes: dict[str, str]
    qualityLevels: list[dict[str, str]]

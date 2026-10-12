from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GameFolder:
    root: Path

    @property
    def videolist(self) -> Path:
        return self.root / "data" / "videoList.rmdj"

    @property
    def episodes(self) -> Path:
        return self.root / "videos" / "episodes"

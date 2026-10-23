from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GameFolder:
    root: Path

    @property
    def videolist(self) -> Path:
        """The game's list of episodes and their manifest URLs."""
        return self.root / "data" / "videoList.rmdj"

    @property
    def episodes(self) -> Path:
        """The folder QuantumStreamer reads the episodes' files from."""
        return self.root / "videos" / "episodes"

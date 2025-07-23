from abc import ABC, abstractmethod


class BaseManifest(ABC):

    @abstractmethod
    def save(self, path, streams) -> None:
        raise NotImplementedError("This method should be implemented by subclasses.")

from abc import ABC, abstractmethod


class Strategy(ABC):
    @abstractmethod
    def try_defend(self, left: str, right: str) -> bool: ...

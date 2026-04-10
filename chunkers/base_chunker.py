from __future__ import annotations

from abc import ABC, abstractmethod


class BaseChunker(ABC):
    @abstractmethod
    def chunk(self, text: str) -> list[dict]:
        raise NotImplementedError

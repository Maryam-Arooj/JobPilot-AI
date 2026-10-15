from abc import ABC, abstractmethod
from typing import Dict

class DocumentParser(ABC):
    @abstractmethod
    def parse(self, file_bytes: bytes, filename: str) -> Dict:
        pass

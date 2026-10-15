from abc import ABC, abstractmethod
from typing import List, Dict, Any

class JobSearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        pass

class JobPageExtractor(ABC):
    @abstractmethod
    def extract(self, url: str) -> Dict[str, Any]:
        pass

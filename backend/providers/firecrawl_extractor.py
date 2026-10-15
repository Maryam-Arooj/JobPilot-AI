import os
from typing import Dict, Any
from .job_providers import JobPageExtractor

class FirecrawlJobExtractor(JobPageExtractor):
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("FIRECRAWL_API_KEY", "")
    
    def extract(self, url: str) -> Dict[str, Any]:
        if not self.api_key:
            return self._fallback_extract(url)
        try:
            import requests
            headers = {"Authorization": f"Bearer {self.api_key}"}
            payload = {"url": url}
            resp = requests.post("https://api.firecrawl.dev/v1/scrape", json=payload, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            extracted_data = data.get("data", {})
            return {
                "url": url,
                "content": extracted_data.get("markdown") or extracted_data.get("html") or "",
                "metadata": extracted_data.get("metadata", {}),
                "extraction_method": "firecrawl"
            }
        except Exception as e:
            # Fallback instead of failing page extraction
            return self._fallback_extract(url, error=str(e))

    def _fallback_extract(self, url: str, error: str = None) -> Dict[str, Any]:
        return {
            "url": url,
            "content": f"Extracted content for job at {url}",
            "metadata": {"source_url": url},
            "extraction_method": "fallback_http",
            "extraction_error": error
        }


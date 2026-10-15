import os
from typing import List, Dict, Any
from .job_providers import JobSearchProvider

class SerpJobSearchProvider(JobSearchProvider):
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("SERPAPI_KEY") or os.getenv("SERP_API_KEY", "")

    def search(self, query: str, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        if not self.api_key:
            raise RuntimeError(
                "SERP API key not configured. Set SERPAPI_KEY in backend/.env to enable live job search."
            )
        import requests
        # Only pass params accepted by SerpAPI
        params = {
            "engine": "google_jobs",
            "q": query,
            "api_key": self.api_key,
        }
        # Add location if provided — only as a clean string
        if filters and isinstance(filters, dict):
            loc = filters.get("location") or filters.get("country")
            if loc and isinstance(loc, str):
                params["location"] = loc

        resp = requests.get("https://serpapi.com/search", params=params, timeout=15)
        if resp.status_code != 200:
            raise RuntimeError(
                f"SerpAPI returned HTTP {resp.status_code}: {resp.text[:300]}"
            )
        data = resp.json()
        jobs = data.get("jobs_results", [])
        return jobs  # Return real results — empty list if no jobs found

# Alias for backwards compatibility
SerpJobSearchTool = SerpJobSearchProvider

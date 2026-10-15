import os
from typing import List, Dict, Any
from .job_providers import JobSearchProvider

class ApifyJobSource(JobSearchProvider):
    def __init__(self, api_token: str = None, actor_id: str = None):
        self.api_token = api_token or os.getenv("APIFY_API_TOKEN", "") or os.getenv("APIFY_API_KEY", "")
        self.actor_id = actor_id or os.getenv("APIFY_ACTOR_ID", "curious_coder~linkedin-jobs-scraper")
        # Replace slashes with tildes if necessary for Apify endpoint URL
        self.actor_slug = self.actor_id.replace("/", "~")

    def search(self, query: str, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        if not self.api_token:
            raise RuntimeError(
                "Apify API token not configured. Set APIFY_API_TOKEN in backend/.env to enable LinkedIn job scraping."
            )
        import requests
        url = f"https://api.apify.com/v2/acts/{self.actor_slug}/run-sync-get-dataset-items?token={self.api_token}"
        payload = {"queries": [query], "limit": 10}

        # Add location filter if provided
        if filters and isinstance(filters, dict):
            loc = filters.get("location") or filters.get("country")
            if loc:
                payload["location"] = str(loc)

        resp = requests.post(url, json=payload, timeout=60)
        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"Apify returned HTTP {resp.status_code}: {resp.text[:300]}"
            )
        data = resp.json()
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            return data.get("items", []) or data.get("data", [])
        return []

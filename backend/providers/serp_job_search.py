"""SerpAPI Google Jobs provider — returns jobs in JobPilot's raw job shape."""
import logging
import os
import re
from typing import Any, Dict, List, Optional

import requests

from .job_providers import JobSearchProvider

logger = logging.getLogger(__name__)
SERP_URL = "https://serpapi.com/search"


def _highlights(job: Dict[str, Any], title_words: tuple) -> List[str]:
    items: List[str] = []
    for h in job.get("job_highlights") or []:
        if any(w in (h.get("title") or "").lower() for w in title_words):
            items.extend(str(i).strip() for i in h.get("items") or [] if str(i).strip())
    return items


def adapt_serp_job(job: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """SerpAPI google_jobs result -> raw job dict understood by services.job_normalizer."""
    title, company = (job.get("title") or "").strip(), (job.get("company_name") or "").strip()
    if not title or not company:
        return None
    ext = job.get("detected_extensions") or {}
    apply = [o.get("link") for o in job.get("apply_options") or [] if o.get("link")]
    url = (apply[0] if apply else None) or job.get("share_link") or next(
        (l.get("link") for l in job.get("related_links") or [] if l.get("link")), "")
    return {
        "title": title,
        "company": company,
        "location": (job.get("location") or "").strip(),
        "remote": bool(ext.get("work_from_home")) or "remote" in (job.get("location") or "").lower(),
        "employment_type": ext.get("schedule_type"),
        "salary": ext.get("salary"),
        "posted_at": ext.get("posted_at"),
        "description": job.get("description") or "",
        "requirements": _highlights(job, ("qualification", "requirement")),
        "responsibilities": _highlights(job, ("responsibilit",)),
        "application_url": url,
        "source": "serpapi:google_jobs",
        "via": job.get("via"),
        "external_id": job.get("job_id"),
    }


class SerpJobSearchProvider(JobSearchProvider):
    def __init__(self, api_key: str = None, timeout: float = 20):
        self.api_key = api_key or os.getenv("SERPAPI_KEY") or os.getenv("SERP_API_KEY", "")
        self.timeout = timeout
        self.last_note = ""

    def _call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        resp = requests.get(SERP_URL, params={**params, "api_key": self.api_key}, timeout=self.timeout)
        if resp.status_code != 200:
            # Body may echo the request; never include the URL (it contains the key).
            raise RuntimeError(f"SerpAPI returned HTTP {resp.status_code}")
        return resp.json()

    def search(self, query: str, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        if not self.api_key:
            raise RuntimeError("SerpAPI key not configured (SERPAPI_KEY in backend/.env)")
        filters = filters or {}
        location = (filters.get("location") or "").strip()
        base = {"engine": "google_jobs", "q": query, "hl": "en"}
        attempts = []
        if location and location.lower() not in ("remote", "remote worldwide", "all"):
            attempts.append({**base, "location": location})
        # Google Jobs often answers "no results" for a location string it doesn't recognise; the
        # location inside the query text ("... in Lahore") usually works, so try that as well.
        q_with_loc = query if (not location or location.lower() in query.lower()) else f"{query} {location}"
        attempts.append({**base, "q": q_with_loc})
        self.last_note = ""
        for params in attempts:
            data = self._call(params)
            jobs = [j for j in (adapt_serp_job(r) for r in data.get("jobs_results") or []) if j]
            if jobs:
                return jobs
            if data.get("error"):
                self.last_note = str(data["error"])[:200]
        return []


SerpJobSearchTool = SerpJobSearchProvider

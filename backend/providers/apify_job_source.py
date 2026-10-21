"""Apify LinkedIn Jobs Scraper (curious_coder~linkedin-jobs-scraper) — raw job dicts for the normalizer."""
import os
from typing import Any, Dict, List, Optional

import requests

from .job_providers import JobSearchProvider


def _first(d: Dict[str, Any], *keys: str) -> Any:
    for k in keys:
        v = d.get(k)
        if v not in (None, "", [], {}):
            return v
    return None


def adapt_apify_item(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """One dataset item -> raw job dict, or None for error/empty items (never saved as a job)."""
    if not isinstance(item, dict) or item.get("error") or item.get("errorMessage") or item.get("#error"):
        return None
    title = _first(item, "title", "jobTitle", "position")
    company = _first(item, "companyName", "company", "company_name")
    if isinstance(company, dict):
        company = company.get("name")
    if not title or not company:
        return None
    location = _first(item, "location", "jobLocation", "place") or ""
    return {
        "title": str(title).strip(),
        "company": str(company).strip(),
        "location": str(location).strip(),
        "remote": "remote" in str(location).lower() or bool(item.get("remoteAllowed") or item.get("workRemoteAllowed")),
        "employment_type": _first(item, "employmentType", "contractType"),
        "seniority": _first(item, "seniorityLevel", "experienceLevel"),
        "salary": _first(item, "salary", "salaryInfo"),
        "posted_at": _first(item, "postedAt", "publishedAt", "postedTime"),
        "description": str(_first(item, "descriptionText", "description", "jobDescription") or ""),
        "application_url": _first(item, "applyUrl", "link", "jobUrl", "url") or "",
        "source": "apify:linkedin",
        "industry": _first(item, "industries", "companyIndustry"),
        "external_id": _first(item, "id", "jobId"),
        # real facts LinkedIn shows on the job/company page (used by the Email Agent; never invented)
        "company_website": _first(item, "companyWebsite", "companyUrl", "website") or "",
        "company_linkedin": _first(item, "companyLinkedinUrl", "companyLinkedInUrl", "companyLink") or "",
        "poster_name": _first(item, "jobPosterName", "posterName", "recruiterName") or "",
        "poster_title": _first(item, "jobPosterTitle", "posterTitle", "recruiterTitle") or "",
        "poster_url": _first(item, "jobPosterProfileUrl", "posterProfileUrl", "recruiterProfileUrl") or "",
    }


class ApifyJobSource(JobSearchProvider):
    def __init__(self, api_token: str = None, actor_id: str = None, timeout: float = None):
        self.api_token = api_token or os.getenv("APIFY_API_TOKEN", "") or os.getenv("APIFY_API_KEY", "")
        self.actor_id = (actor_id or os.getenv("APIFY_ACTOR_ID", "curious_coder~linkedin-jobs-scraper")).replace("/", "~")
        self.timeout = timeout or float(os.getenv("APIFY_TIMEOUT", "45"))
        self.limit = int(os.getenv("APIFY_LIMIT", "10"))
        self.last_note = ""

    def search(self, query: str, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        if not self.api_token:
            raise RuntimeError("Apify token not configured (APIFY_API_TOKEN in backend/.env)")
        filters = filters or {}
        remote = bool(filters.get("remote"))
        payload: Dict[str, Any] = {"keywords": f"{query} remote" if remote else query,
                                   "limitPerSource": self.limit, "scrapeCompany": False}
        loc = (filters.get("location") or "").strip()
        if remote and not loc:
            payload["location"] = "Worldwide"
        elif loc and loc.lower() not in ("all", "remote worldwide"):
            payload["location"] = loc
        resp = requests.post(
            f"https://api.apify.com/v2/acts/{self.actor_id}/run-sync-get-dataset-items",
            params={"token": self.api_token, "timeout": int(self.timeout)},
            json=payload, timeout=self.timeout + 10,
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Apify returned HTTP {resp.status_code}")
        data = resp.json()
        items = data if isinstance(data, list) else (data.get("items") or data.get("data") or [])
        jobs = [j for j in (adapt_apify_item(i) for i in items) if j]
        errors = [i for i in items if isinstance(i, dict) and (i.get("error") or i.get("errorMessage"))]
        self.last_note = (f"{len(errors)} error item(s) from Apify were skipped" if errors else "")
        return jobs

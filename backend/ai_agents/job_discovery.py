"""Job Agent — discovery: live search on SerpAPI (Google Jobs) and Apify (LinkedIn) in parallel."""
import contextvars
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from ..services.agent_runs import run_log, run_step, tool_call
from ..services.job_normalizer import deduplicate_jobs, normalize_job

LOCATION_HINTS = {"pakistan": "Pakistan", "lahore": "Lahore, Pakistan", "karachi": "Karachi, Pakistan",
                  "islamabad": "Islamabad, Pakistan"}


class JobDiscoveryAgent:
    def __init__(self):
        from ..providers.apify_job_source import ApifyJobSource
        from ..providers.serp_job_search import SerpJobSearchProvider
        self.apify = ApifyJobSource()
        self.serp = SerpJobSearchProvider()

    def discover_intent(self, natural_query: str, career_profile: Dict[str, Any], location: Optional[str] = None,
                        remote: bool = False) -> Dict[str, Any]:
        q = natural_query.strip()
        filters: Dict[str, Any] = {}
        if remote or re.search(r"\bremote\b", q, re.I):
            filters["remote"] = True
            q = re.sub(r"\s*\bremote\b\s*", " ", q, flags=re.I).strip() or q
        if location:
            filters["location"] = location
        else:
            for word, loc in LOCATION_HINTS.items():
                if word in q.lower():
                    filters["location"] = loc
        return {"original_query": natural_query, "search_queries": [q], "filters": filters}

    def _run_provider(self, name: str, provider, query: str, filters: Dict[str, Any]):
        where = ("remote" if filters.get("remote") else "") + (f" location={filters.get('location')!r}" if filters.get("location") else "")
        with tool_call(f"{name}", f"query={query!r} {where}".strip()) as tc:
            jobs = provider.search(query, filters)
            note = getattr(provider, "last_note", "")
            tc["summary"] = f"{len(jobs)} jobs" + (f" ({note})" if note else "")
        return jobs

    def discover(self, natural_query: str, career_profile: Dict[str, Any], location: Optional[str] = None,
                 remote: bool = False) -> Dict[str, Any]:
        intent = self.discover_intent(natural_query, career_profile, location, remote)
        query, filters = intent["search_queries"][0], intent["filters"]
        providers = [("serpapi:google_jobs", self.serp), ("apify:linkedin_jobs", self.apify)]
        ctx = contextvars.copy_context()
        results: Dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=len(providers)) as pool:
            futures = {name: pool.submit(ctx.copy().run, self._run_provider, name, prov, query, filters)
                       for name, prov in providers}
            for name, fut in futures.items():
                try:
                    results[name] = fut.result()
                except Exception as e:  # provider failure is reported, never hidden
                    results[name] = e
        all_jobs: List[Dict[str, Any]] = []
        provider_errors: List[str] = []
        provider_status: Dict[str, Any] = {}
        for name, res in results.items():
            if isinstance(res, Exception):
                provider_errors.append(f"{name}: {str(res)[:200]}")
                provider_status[name] = {"ok": False, "error": str(res)[:200]}
                run_log("warn", f"{name} failed: {str(res)[:200]}")
            else:
                all_jobs.extend(res)
                provider_status[name] = {"ok": True, "jobs": len(res)}

        if not all_jobs and len(provider_errors) == len(providers):
            from fastapi import HTTPException
            raise HTTPException(status_code=503, detail=f"No jobs returned from live providers. Errors: {'; '.join(provider_errors)}")

        run_step("Normalise and remove duplicates", 2, 3)
        normalized = [normalize_job(j, j.get("source", "provider")) for j in all_jobs]
        normalized = [j for j in normalized if j["title"] and j["company"]]
        deduped = deduplicate_jobs(normalized)
        run_log("info", f"{len(all_jobs)} jobs from providers, {len(deduped)} after removing duplicates")
        return {"intent": intent, "results": deduped, "provider_errors": provider_errors, "provider_status": provider_status}

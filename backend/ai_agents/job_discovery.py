from typing import Dict, Any, List
from ..services.job_normalizer import normalize_job, deduplicate_jobs

class JobDiscoveryAgent:
    def __init__(self):
        from ..providers.apify_job_source import ApifyJobSource
        from ..providers.serp_job_search import SerpJobSearchProvider
        from ..providers.firecrawl_extractor import FirecrawlJobExtractor
        self.apify = ApifyJobSource()
        self.serp = SerpJobSearchProvider()
        self.extractor = FirecrawlJobExtractor()

    def discover_intent(self, natural_query: str, career_profile: Dict[str, Any]) -> Dict[str, Any]:
        query_lower = natural_query.lower()
        intent = {
            "original_query": natural_query,
            "search_queries": [natural_query],
            "filters": {}
        }
        if "remote" in query_lower:
            intent["filters"]["remote"] = True
        if "pakistan" in query_lower:
            intent["filters"]["location"] = "Pakistan"
        if "lahore" in query_lower:
            intent["filters"]["location"] = "Lahore, Pakistan"
        if "matching my profile" in query_lower or "my profile" in query_lower:
            title = (
                career_profile.get("professional", {}).get("target_role", "") or
                career_profile.get("professional", {}).get("title", "")
            )
            if title:
                intent["search_queries"].append(f"{title} jobs")
        return intent

    def _enrich(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich job data with Firecrawl — skip if no URL to avoid timeouts."""
        url = job.get("application_url") or job.get("url") or job.get("source_url")
        if not url or "example.com" in url:
            return job
        try:
            extracted = self.extractor.extract(url)
            for k in ["title", "company", "description", "requirements", "location", "remote"]:
                if extracted.get(k):
                    job[k] = extracted[k]
            job["extraction_provenance"] = {"source": "firecrawl", "url": url}
        except Exception as e:
            # Non-blocking — proceed with provider-supplied data
            job["extraction_provenance"] = {"source": "provider_raw", "url": url}
        return job

    def discover(self, natural_query: str, career_profile: Dict[str, Any]) -> Dict[str, Any]:
        intent = self.discover_intent(natural_query, career_profile)
        all_jobs = []
        provider_errors = []

        for q in intent["search_queries"]:
            # Try SERP — real API call
            try:
                serp_results = self.serp.search(q, intent["filters"])
                if serp_results and isinstance(serp_results, list):
                    all_jobs.extend(serp_results)
            except Exception as e:
                provider_errors.append(f"SERP: {str(e)}")

            # Try Apify — real API call
            try:
                apify_results = self.apify.search(q, intent["filters"])
                if apify_results and isinstance(apify_results, list):
                    all_jobs.extend(apify_results)
            except Exception as e:
                provider_errors.append(f"Apify: {str(e)}")

        # If both providers returned zero results AND there are errors, raise so frontend knows
        if not all_jobs and provider_errors:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=503,
                detail=f"No jobs returned from live providers. Errors: {'; '.join(provider_errors)}"
            )

        # If providers returned nothing but no errors (empty results), return empty — no mock
        enriched = [self._enrich(j) for j in all_jobs]
        normalized = [normalize_job(j, j.get("source", "serp")) for j in enriched]
        deduped = deduplicate_jobs(normalized)
        return {"intent": intent, "results": deduped, "provider_errors": provider_errors}

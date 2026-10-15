import re
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
from typing import Dict, Any, List

def canonicalize_url(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(url.strip())
        # Lowercase scheme & netloc, strip trailing slash
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip("/")
        # Filter out tracking query parameters (utm_*, ref, source, etc.)
        filtered_query = [
            (k, v) for k, v in parse_qsl(parsed.query)
            if not (k.lower().startswith("utm_") or k.lower() in ("ref", "fbclid", "gclid", "source"))
        ]
        query = urlencode(filtered_query)
        return urlunparse((scheme, netloc, path, parsed.params, query, ""))
    except Exception:
        return url.strip().lower()

def normalize_job(raw: Dict[str, Any], provider: str) -> Dict[str, Any]:
    title = (raw.get("title") or raw.get("job_title") or "").strip()
    company = (raw.get("company") or raw.get("company_name") or "").strip()
    location = (raw.get("location") or raw.get("job_location") or "").strip()
    app_url = raw.get("application_url") or raw.get("url") or raw.get("link") or ""
    c_url = canonicalize_url(app_url)
    
    norm_title = re.sub(r'\s+', ' ', title.lower())
    norm_company = re.sub(r'\s+', ' ', company.lower())
    norm_location = re.sub(r'\s+', ' ', location.lower())
    
    # Remote detection
    is_remote = bool(raw.get("remote")) or "remote" in norm_location or "remote" in norm_title
    
    # Requirement arrays
    reqs = raw.get("requirements") or []
    if isinstance(reqs, str):
        reqs = [r.strip() for r in reqs.split("\n") if r.strip()]
        
    pref = raw.get("preferred_skills") or []
    if isinstance(pref, str):
        pref = [p.strip() for p in pref.split("\n") if p.strip()]
        
    resp = raw.get("responsibilities") or []
    if isinstance(resp, str):
        resp = [r.strip() for r in resp.split("\n") if r.strip()]

    techs = raw.get("technologies") or raw.get("skills") or []
    if isinstance(techs, str):
        techs = [t.strip() for t in techs.split(",") if t.strip()]

    source_record = {
        "provider": provider,
        "source_url": app_url,
        "raw_data": raw
    }

    return {
        "title": title,
        "company": company,
        "location": location,
        "remote": is_remote,
        "employment_type": raw.get("employment_type", "Full-time"),
        "salary": raw.get("salary") or (raw.get("detected_extensions", {}).get("salary") if isinstance(raw.get("detected_extensions"), dict) else None),
        "description": raw.get("description", ""),
        "requirements": reqs,
        "preferred_skills": pref,
        "responsibilities": resp,
        "application_url": app_url,
        "canonical_application_url": c_url,
        "source": provider,
        "source_url": app_url,
        "posted_at": raw.get("posted_at"),
        "retrieved_at": raw.get("retrieved_at"),
        "extraction_method": raw.get("extraction_method", "provider"),
        "technologies": techs,
        "seniority": raw.get("seniority", "Mid-Senior"),
        "experience_years": raw.get("experience_years"),
        "industry": raw.get("industry", "Technology"),
        "job_type": raw.get("job_type", "Full-time"),
        "country": raw.get("country", ""),
        "city": raw.get("city", ""),
        "normalized_title": norm_title,
        "normalized_company": norm_company,
        "extraction_provenance": raw.get("extraction_provenance"),
        "extraction_error": raw.get("extraction_error"),
        "sources": [source_record]
    }

def calculate_text_similarity(text1: str, text2: str) -> float:
    """Calculates token Jaccard similarity between two text descriptions."""
    if not text1 or not text2:
        return 0.0
    tokens1 = set(re.findall(r'\w+', text1.lower()))
    tokens2 = set(re.findall(r'\w+', text2.lower()))
    if not tokens1 or not tokens2:
        return 0.0
    intersection = len(tokens1.intersection(tokens2))
    union = len(tokens1.union(tokens2))
    return intersection / union if union > 0 else 0.0

def deduplicate_jobs(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    4-Step Deterministic Deduplication:
    1. Exact application URL match
    2. Canonicalized application URL match
    3. Company + Title + Location match
    4. Description text similarity match (Jaccard >= 0.80)
    Merges source references into canonical job upon deduplication.
    """
    deduped: List[Dict[str, Any]] = []

    for new_job in jobs:
        new_app_url = new_job.get("application_url", "").strip()
        new_c_url = new_job.get("canonical_application_url", "").strip()
        new_company = new_job.get("normalized_company", "")
        new_title = new_job.get("normalized_title", "")
        new_location = new_job.get("location", "").lower()
        new_desc = new_job.get("description", "")

        matched_existing = None

        for existing in deduped:
            ex_app_url = existing.get("application_url", "").strip()
            ex_c_url = existing.get("canonical_application_url", "").strip()
            ex_company = existing.get("normalized_company", "")
            ex_title = existing.get("normalized_title", "")
            ex_location = existing.get("location", "").lower()
            ex_desc = existing.get("description", "")

            # Step 1: Exact application URL
            if new_app_url and ex_app_url and new_app_url == ex_app_url:
                matched_existing = existing
                break

            # Step 2: Canonicalized URL
            if new_c_url and ex_c_url and new_c_url == ex_c_url:
                matched_existing = existing
                break

            # Step 3: Company + Title + Location
            if new_company and ex_company and new_title and ex_title:
                if new_company == ex_company and new_title == ex_title and (not new_location or not ex_location or new_location == ex_location):
                    matched_existing = existing
                    break

            # Step 4: Description text similarity
            if new_company == ex_company and calculate_text_similarity(new_desc, ex_desc) >= 0.80:
                matched_existing = existing
                break

        if matched_existing:
            # Merge sources list
            existing_sources = matched_existing.setdefault("sources", [])
            for src in new_job.get("sources", []):
                if src not in existing_sources:
                    existing_sources.append(src)
        else:
            deduped.append(new_job)

    return deduped


"""Company research from real sources only (Email Agent).

1. Find the official website: the job's apply link if it is the company's own domain, otherwise a
   SerpAPI Google search (knowledge graph website or a result whose domain matches the company name).
   Job boards, social networks and directories are never treated as the official site.
2. Firecrawl reads the homepage (and /about if the homepage is thin).
3. The AI summarises ONLY that page; every sentence/item must be supported by the page text (grounding),
   otherwise it is dropped. Nothing found -> status "not_found" with empty fields. Nothing is invented.
"""
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

from ..services.agent_runs import run_log, run_warn, tool_call

logger = logging.getLogger(__name__)

NOT_OFFICIAL = ("linkedin.", "indeed.", "glassdoor.", "rozee.", "bayt.", "monster.", "ziprecruiter.", "greenhouse.io",
                "lever.co", "workday", "myworkdayjobs", "smartrecruiters", "bamboohr", "google.", "facebook.", "twitter.",
                "x.com", "instagram.", "youtube.", "wikipedia.", "crunchbase.", "zoominfo.", "mustakbil", "careerjet",
                "simplyhired", "naukri", "wellfound", "angel.co", "builtin", "ashbyhq", "recruitee", "workable.",
                "jobvite", "icims", "taleo", "breezy", "teamtailor", "dice.", "remoteok", "weworkremotely", "remotive",
                "jooble", "talent.com", "adzuna", "trabajo", "jobstreet", "naukrigulf", "gulftalent", "dailymotion",
                "github.com", "medium.com", "bloomberg.", "reuters.", "forbes.", "yelp.", "pinterest.", "tiktok.",
                "careers-page", "hirist", "foundit", "upwork", "fiverr", "freelancer.")


def _domain(url: str) -> str:
    try:
        host = urlparse(url if "://" in url else f"https://{url}").netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _root(url: str) -> str:
    d = _domain(url)
    for prefix in ("careers.", "jobs.", "apply.", "career."):
        if d.startswith(prefix) and d.count(".") >= 2:
            d = d[len(prefix):]
    return f"https://{d}" if d else ""


def _is_official_candidate(url: str) -> bool:
    d = _domain(_root(url))
    return bool(d) and not any(bad in d for bad in NOT_OFFICIAL)


def _name_tokens(company: str) -> List[str]:
    words = re.findall(r"[a-z0-9]+", company.lower())
    stop = {"inc", "ltd", "llc", "pvt", "private", "limited", "the", "co", "corp", "corporation", "company", "group",
            "technologies", "technology", "solutions", "services", "international", "global", "pakistan", "and"}
    return [w for w in words if w not in stop and len(w) > 2] or words[:1]


def _domain_matches_company(url: str, company: str) -> bool:
    root = _domain(_root(url))
    d = re.sub(r"[^a-z0-9]", "", root.split(".")[0] if root else "")
    full = re.sub(r"[^a-z0-9]", "", company.lower())
    return bool(d) and (d in full or full.startswith(d) or any(t in d for t in _name_tokens(company)))


class FirecrawlCompanyResearchProvider:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("FIRECRAWL_API_KEY", "")
        self.serp_key = os.getenv("SERPAPI_KEY") or os.getenv("SERP_API_KEY", "")

    # ---- 1. official website ------------------------------------------------------------
    def find_official_website(self, company: str, job_url: Optional[str] = None,
                              known: Optional[str] = None) -> Tuple[Optional[str], str]:
        if known and _is_official_candidate(known) and _domain_matches_company(known, company):
            return _root(known), "saved company website"
        if job_url and _is_official_candidate(job_url) and _domain_matches_company(job_url, company):
            return _root(job_url), "the job's apply link (company domain)"
        if not self.serp_key:
            run_warn("Company research: no SerpAPI key, so the official website could not be looked up.")
            return None, "no search key"
        with tool_call("serpapi:google", f"official website of {company!r}") as tc:
            resp = requests.get("https://serpapi.com/search", timeout=20, params={
                "engine": "google", "q": f"{company} official website", "num": 8, "hl": "en", "api_key": self.serp_key})
            if resp.status_code != 200:
                raise RuntimeError(f"SerpAPI returned HTTP {resp.status_code}")
            data = resp.json()
            kg = (data.get("knowledge_graph") or {}).get("website")
            candidates = ([kg] if kg else []) + [r.get("link") for r in data.get("organic_results") or [] if r.get("link")]
            for url in candidates:
                if _is_official_candidate(url) and _domain_matches_company(url, company):
                    tc["summary"] = f"found {_root(url)}"
                    return _root(url), "Google search"
            tc["summary"] = f"no official website among {len(candidates)} results"
        return None, "not found"

    # ---- 2. read the site -------------------------------------------------------------
    def scrape(self, url: str) -> str:
        if not self.api_key:
            run_warn("Company research: FIRECRAWL_API_KEY is missing, so the website could not be read.")
            return ""
        with tool_call("firecrawl:scrape", url) as tc:
            resp = requests.post("https://api.firecrawl.dev/v1/scrape", timeout=30,
                                 headers={"Authorization": f"Bearer {self.api_key}"},
                                 json={"url": url, "formats": ["markdown"], "onlyMainContent": True})
            if resp.status_code != 200:
                raise RuntimeError(f"Firecrawl returned HTTP {resp.status_code}")
            md = ((resp.json() or {}).get("data") or {}).get("markdown") or ""
            md = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", md)            # images
            md = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", md)          # keep link text only
            md = re.sub(r"\n{3,}", "\n\n", md).strip()
            tc["summary"] = f"{len(md)} characters read"
        return md[:15000]

    # ---- 3. grounded summary ----------------------------------------------------------
    def summarize(self, company: str, page: str) -> Dict[str, Any]:
        from ..ai_agents.profile_agent import _Source
        from ..services.nvidia_llm import LLMError, call_nvidia_json
        system = ("You summarise a company's own website for a job applicant. Use ONLY facts written in the page. "
                  "Copy product names exactly. If something is not on the page, leave it empty. Return JSON: "
                  '{"overview": str (1-2 sentences), "industry": str, "products_services": [str], '
                  '"technology_info": [str], "mission_info": str}')
        try:
            raw = call_nvidia_json(f"Company: {company}\n<page>\n{page[:12000]}\n</page>", system_prompt=system,
                                   temperature=0.0, max_tokens=700, timeout=45)
        except LLMError as e:
            run_warn(f"AI summary unavailable ({e}); only the page itself is kept as the source.")
            return {}
        if not isinstance(raw, dict):
            return {}
        src = _Source(page)

        def ok_sentence(s: Any) -> bool:
            return isinstance(s, str) and s.strip() and src.mostly_has(s, 0.6)

        def ok_item(s: Any) -> bool:
            return isinstance(s, str) and 1 < len(s) <= 120 and (src.has(s) or src.mostly_has(s, 0.75))

        out = {
            "overview": raw.get("overview") if ok_sentence(raw.get("overview")) else "",
            "industry": raw.get("industry") if isinstance(raw.get("industry"), str) and src.has(raw["industry"]) else "",
            "products_services": [s for s in raw.get("products_services") or [] if ok_item(s)][:8],
            "technology_info": [s for s in raw.get("technology_info") or [] if ok_item(s)][:8],
            "mission_info": raw.get("mission_info") if ok_sentence(raw.get("mission_info")) else "",
        }
        total = sum(1 for k in ("overview", "industry", "mission_info") if raw.get(k)) + \
            len(raw.get("products_services") or []) + len(raw.get("technology_info") or [])
        kept = sum(1 for k in ("overview", "industry", "mission_info") if out[k]) + \
            len(out["products_services"]) + len(out["technology_info"])
        if total > kept:
            run_log("warn", f"Company research: {total - kept} AI statement(s) not supported by the website were removed")
        return out

    def research_company(self, company_name: str, official_website: str = None, job_url: str = None) -> Dict[str, Any]:
        empty = {"company_name": company_name, "official_website": None, "overview": "", "industry": "",
                 "products_services": [], "technology_info": [], "engineering_info": "", "mission_info": "",
                 "recent_news": [], "careers_url": "", "sources": [], "claims": []}
        try:
            site, how = self.find_official_website(company_name, job_url, official_website)
        except Exception as e:
            run_warn(f"Company website lookup failed: {e}")
            return {**empty, "status": "unavailable", "message": "The company website could not be looked up right now."}
        if not site:
            return {**empty, "status": "not_found",
                    "message": f"No official website for {company_name} could be found, so no company facts are used."}
        try:
            page = self.scrape(site)
            if len(page) < 500:
                about = self.scrape(site.rstrip("/") + "/about")
                if len(about) > len(page):
                    site, page = site.rstrip("/") + "/about", about
        except Exception as e:
            run_warn(f"Reading {site} failed: {e}")
            page = ""
        if not page:
            return {**empty, "official_website": site, "status": "unavailable",
                    "message": f"Found {site} but could not read it, so no company facts are used.",
                    "sources": [{"source_url": site, "provider": how, "raw_data": {}}]}
        summary = self.summarize(company_name, page)
        claims = ([{"claim_text": summary["overview"], "source_url": site, "fact_type": "overview"}] if summary.get("overview") else []) + \
            [{"claim_text": p, "source_url": site, "fact_type": "product"} for p in summary.get("products_services", [])] + \
            [{"claim_text": t, "source_url": site, "fact_type": "technology"} for t in summary.get("technology_info", [])] + \
            ([{"claim_text": summary["mission_info"], "source_url": site, "fact_type": "mission"}] if summary.get("mission_info") else [])
        return {
            **empty, **{k: v for k, v in summary.items() if v},
            "official_website": site,
            "careers_url": "",
            "status": "found" if claims else "unavailable",
            "message": "" if claims else f"{site} was read, but no usable company facts were found on it.",
            "sources": [{"source_url": site, "provider": f"firecrawl ({how})", "raw_data": {"characters": len(page)}}],
            "claims": claims,
        }

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
            # Google's company panel names the website itself, even when the domain differs from the name
            if kg and _is_official_candidate(kg):
                tc["summary"] = f"found {_root(kg)} (Google company panel)"
                return _root(kg), "Google company panel"
            # a top result whose title carries the full company name (e.g. "Cedar Global Solutions | Home" on cedargs.com)
            full = re.sub(r"[^a-z0-9]", "", company.lower())
            for r in (data.get("organic_results") or [])[:3]:
                title = re.sub(r"[^a-z0-9]", "", (r.get("title") or "").lower())
                if r.get("link") and _is_official_candidate(r["link"]) and len(full) >= 6 and full in title:
                    tc["summary"] = f"found {_root(r['link'])} (result title matches)"
                    return _root(r["link"]), "Google search (title match)"
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


# ---- recruiter / company contact emails (real addresses only) ---------------------------
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
SKIP_LOCAL = ("noreply", "no-reply", "donotreply", "do-not-reply", "privacy", "abuse", "legal", "dpo", "gdpr",
              "unsubscribe", "postmaster", "webmaster", "mailer", "example", "test", "user", "name", "email",
              "yourname", "someone", "sentry", "wixpress")
RANK = [("hiring", ("hr", "careers", "career", "jobs", "job", "recruit", "recruiting", "recruitment", "talent",
                    "hiring", "hire", "people", "apply", "cv", "resume", "join")),
        ("general", ("info", "contact", "hello", "hi", "office", "admin", "team", "enquiries", "inquiries", "general"))]


def _email_kind(email: str) -> Optional[str]:
    local = email.split("@")[0].lower()
    if any(s == local or local.startswith(s) for s in SKIP_LOCAL) or email.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
        return None
    for kind, words in RANK:
        if any(local == w or local.startswith(w) or local.endswith(w) for w in words):
            return kind
    return "other"


def extract_emails(text: str) -> List[str]:
    out: List[str] = []
    for e in EMAIL_RE.findall(text or ""):
        e = e.strip(".").lower()
        if e not in out and _email_kind(e):
            out.append(e)
    return out


def rank_contacts(found: List[Dict[str, str]]) -> List[Dict[str, str]]:
    order = {"job_posting": 0, "hiring": 1, "general": 2, "other": 3}
    seen, out = set(), []
    for c in sorted(found, key=lambda c: (order.get(c["kind"], 9), 0 if c.get("on_site") else 1)):
        if c["email"] not in seen:
            seen.add(c["email"])
            out.append(c)
    return out[:6]


def _scrape_for_contacts(api_key: str, url: str) -> Tuple[str, List[str]]:
    """Firecrawl one page; returns (markdown with mailto links kept, links on the page)."""
    resp = requests.post("https://api.firecrawl.dev/v1/scrape", timeout=20,
                         headers={"Authorization": f"Bearer {api_key}"},
                         json={"url": url, "formats": ["markdown", "links"], "onlyMainContent": False, "timeout": 15000})
    if resp.status_code != 200:
        return "", []
    data = (resp.json() or {}).get("data") or {}
    return data.get("markdown") or "", [l for l in data.get("links") or [] if isinstance(l, str)]


CONTACT_PATH = re.compile(r"(contact|career|jobs|join|hiring|recruit|work-with-us|about|team|reach)", re.I)


def _parallel(funcs: List[Any], max_workers: int = 6) -> List[Any]:
    """Run small network calls at the same time, keeping the agent-run context (dashboard tool calls)."""
    import contextvars
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(contextvars.copy_context().run, f) for f in funcs]
        out = []
        for fut in futures:
            try:
                out.append(fut.result(timeout=30))
            except Exception as e:  # one slow/failed page never blocks the rest
                run_warn(f"Contact search step failed: {e}")
                out.append(None)
        return out


def find_contact_emails(company: str, website: Optional[str]) -> Dict[str, Any]:
    """Look for real contact addresses on the company's own pages and in Google results, all at once.
    On-site addresses are trusted (the company published them); Google addresses only on the company's domain."""
    found: List[Dict[str, str]] = []
    fc_key = os.getenv("FIRECRAWL_API_KEY", "")
    serp_key = os.getenv("SERPAPI_KEY") or os.getenv("SERP_API_KEY", "")
    domain = _domain(website) if website else ""
    scraped: set = set()

    def page_job(url: str):
        def run():
            with tool_call("firecrawl:scrape", f"contact emails on {url}") as tc:
                md, links = _scrape_for_contacts(fc_key, url)
                emails = extract_emails(md)
                tc["summary"] = f"{len(emails)} email(s)"
            return ("page", url, emails, links)
        return run

    def google_job(q: str):
        def run():
            with tool_call("serpapi:google", q[:80]) as tc:
                resp = requests.get("https://serpapi.com/search", timeout=15,
                                    params={"engine": "google", "q": q, "num": 10, "hl": "en", "api_key": serp_key})
                data = resp.json() if resp.status_code == 200 else {}
                hits = []
                for r in data.get("organic_results") or []:
                    text = " ".join(str(r.get(k) or "") for k in ("snippet", "title"))
                    text += " " + " ".join(str(x) for x in (r.get("snippet_highlighted_words") or []))
                    for e in extract_emails(text):
                        ed = e.split("@")[1]
                        if (domain and (ed == domain or ed.endswith("." + domain))) or \
                           (not domain and _domain_matches_company("https://" + ed, company)):
                            hits.append((e, r.get("link") or ""))
                tc["summary"] = f"{len(hits)} matching email(s)"
            return ("google", q, hits, [])
        return run

    hunter_key = os.getenv("HUNTER_API_KEY", "")

    def hunter_job():
        with tool_call("hunter:domain-search", domain) as tc:
            resp = requests.get("https://api.hunter.io/v2/domain-search", timeout=15,
                                params={"domain": domain, "limit": 10, "api_key": hunter_key})
            if resp.status_code != 200:
                raise RuntimeError(f"Hunter returned HTTP {resp.status_code}")
            hits = []
            for e in ((resp.json() or {}).get("data") or {}).get("emails") or []:
                addr = (e.get("value") or "").lower()
                if not addr or not _email_kind(addr) or (e.get("verification") or {}).get("status") == "invalid":
                    continue
                dept = " ".join(str(e.get(k) or "") for k in ("department", "position")).lower()
                hiring = any(w in dept for w in ("hr", "human resources", "recruit", "talent", "hiring", "people"))
                src = next((x.get("uri") for x in e.get("sources") or [] if x.get("uri")), "hunter.io")
                hits.append((addr, src, "hiring" if hiring else None))
            tc["summary"] = f"{len(hits)} published email(s)"
        return ("hunter", domain, hits, [])

    tomba_key, tomba_secret = os.getenv("TOMBA_API_KEY", ""), os.getenv("TOMBA_SECRET", "")

    def tomba_job():
        with tool_call("tomba:domain-search", domain) as tc:
            resp = requests.get("https://api.tomba.io/v1/domain-search", timeout=15, params={"domain": domain},
                                headers={"X-Tomba-Key": tomba_key, "X-Tomba-Secret": tomba_secret})
            if resp.status_code != 200:
                raise RuntimeError(f"Tomba returned HTTP {resp.status_code}")
            hits = []
            for e in ((resp.json() or {}).get("data") or {}).get("emails") or []:
                addr = str(e.get("email") or e.get("value") or "").lower()
                if not addr or not _email_kind(addr) or str((e.get("verification") or {}).get("status")) == "invalid":
                    continue
                dept = " ".join(str(e.get(k) or "") for k in ("department", "position")).lower()
                hiring = any(w in dept for w in ("hr", "human resources", "recruit", "talent", "hiring", "people"))
                src = next((x.get("uri") for x in e.get("sources") or [] if isinstance(x, dict) and x.get("uri")), "tomba.io")
                hits.append((addr, src, "hiring" if hiring else None))
            tc["summary"] = f"{len(hits)} published email(s)"
        return ("hunter", domain, hits, [])

    def web_search_job():
        """Firecrawl search: pages anywhere on the web that mention the company's contact email."""
        with tool_call("firecrawl:search", f"{company} contact email") as tc:
            resp = requests.post("https://api.firecrawl.dev/v1/search", timeout=25,
                                 headers={"Authorization": f"Bearer {fc_key}"},
                                 json={"query": f'"{company}" contact email', "limit": 5,
                                       "scrapeOptions": {"formats": ["markdown"], "onlyMainContent": False}})
            hits = []
            if resp.status_code == 200:
                for r in (resp.json() or {}).get("data") or []:
                    text = " ".join(str(r.get(k) or "") for k in ("markdown", "description", "title"))
                    for e in extract_emails(text):
                        ed = e.split("@")[1]
                        if (domain and (ed == domain or ed.endswith("." + domain))) or \
                           (not domain and _domain_matches_company("https://" + ed, company)):
                            hits.append((e, r.get("url") or ""))
            tc["summary"] = f"{len(hits)} matching email(s)"
        return ("google", "web", hits, [])

    jobs = []
    if domain and hunter_key:
        jobs.append(hunter_job)
    if domain and tomba_key and tomba_secret:
        jobs.append(tomba_job)
    if fc_key:
        jobs.append(web_search_job)
    if website and fc_key:
        for path in ("", "/contact", "/contact-us", "/careers", "/about"):
            url = website.rstrip("/") + path
            scraped.add(url.rstrip("/"))
            jobs.append(page_job(url))
    elif website:
        run_warn("FIRECRAWL_API_KEY is missing, so the company's contact page could not be read.")
    if serp_key:
        if domain:
            jobs.append(google_job(f'"@{domain}"'))
            jobs.append(google_job(f'"@{domain}" careers OR hr OR jobs OR recruitment email'))
        jobs.append(google_job(f'{company} careers email OR "hr email" OR "send your cv" OR "send your resume"'))

    def collect(results):
        more = []
        for res in results:
            if not res:
                continue
            kind, where, items, links = res
            if kind == "page":
                for e in items:
                    found.append({"email": e, "kind": _email_kind(e), "source_url": where, "on_site": True})
                for l in links:
                    if domain and _domain(l) == domain and CONTACT_PATH.search(urlparse(l).path or "") \
                            and l.split("#")[0].rstrip("/") not in scraped:
                        more.append(l.split("#")[0].rstrip("/"))
            elif kind == "hunter":
                for e, link, k in items:
                    found.append({"email": e, "kind": k or _email_kind(e), "source_url": link, "on_site": False})
            else:
                for e, link in items:
                    found.append({"email": e, "kind": _email_kind(e), "source_url": link, "on_site": False})
        return more

    extra = collect(_parallel(jobs))
    if fc_key and extra and not any(c["kind"] == "hiring" for c in found):
        extra = list(dict.fromkeys(extra))[:3]           # second wave: contact/careers pages linked from the site
        scraped.update(extra)
        collect(_parallel([page_job(u) for u in extra]))
    contacts = rank_contacts(found)
    checked = ([f"website {website}"] if website else ["no official website found"]) + \
        (["company pages"] if website and fc_key else []) + (["Google"] if serp_key else []) + \
        (["web search"] if fc_key else []) + (["Hunter.io"] if domain and hunter_key else []) + \
        (["Tomba.io"] if domain and tomba_key and tomba_secret else [])
    return {"contacts": contacts, "checked": checked,
            "message": "" if contacts else (f"{company} does not publish a contact email on its website or in Google results. "
                                            "Big companies usually take applications only through the job's Apply link.")}


def find_job_contact_emails(job_title: str, company: str, urls: List[str]) -> Dict[str, Any]:
    """Recruiter emails written on the job's own public pages (LinkedIn job page, Apply page) and in public
    LinkedIn posts about this job/company found by Google. Any email domain is accepted here, because a
    recruiter may post from Gmail, but only when the page/post is about this company."""
    fc_key = os.getenv("FIRECRAWL_API_KEY", "")
    serp_key = os.getenv("SERPAPI_KEY") or os.getenv("SERP_API_KEY", "")
    comp_l = re.sub(r"[^a-z0-9]", "", (company or "").lower())
    found: List[Dict[str, str]] = []

    def mentions_company(text: str) -> bool:
        t = re.sub(r"[^a-z0-9]", "", (text or "").lower())
        return bool(comp_l) and (comp_l in t or any(tok in t for tok in _name_tokens(company) if len(tok) > 3))

    def page(url: str):
        def run():
            with tool_call("firecrawl:scrape", f"recruiter email on the job page {urlparse(url).netloc}") as tc:
                md, _links = _scrape_for_contacts(fc_key, url)
                emails = extract_emails(md)
                tc["summary"] = f"{len(emails)} email(s)"
            return [(e, url, "the job page") for e in emails]
        return run

    def google(q: str, label: str):
        def run():
            with tool_call("serpapi:google", q[:80]) as tc:
                resp = requests.get("https://serpapi.com/search", timeout=15,
                                    params={"engine": "google", "q": q, "num": 10, "hl": "en", "api_key": serp_key})
                data = resp.json() if resp.status_code == 200 else {}
                hits = []
                for r in data.get("organic_results") or []:
                    text = " ".join(str(r.get(k) or "") for k in ("title", "snippet"))
                    text += " " + " ".join(str(x) for x in (r.get("snippet_highlighted_words") or []))
                    if mentions_company(text):
                        hits += [(e, r.get("link") or "", label) for e in extract_emails(text)]
                tc["summary"] = f"{len(hits)} email(s)"
            return hits
        return run

    jobs = []
    if fc_key:
        for u in dict.fromkeys(u for u in urls if u and u.startswith("http")):
            jobs.append(page(u))
    if serp_key and company:
        jobs.append(google(f'site:linkedin.com "{company}" hiring email OR "send your cv" OR "send cv" OR "share your cv"',
                           "a public LinkedIn post"))
        if job_title:
            jobs.append(google(f'"{company}" "{job_title}" email OR "send your cv" OR "send resume"', "a public post about this job"))
    for res in _parallel(jobs):
        for e, src, label in res or []:
            found.append({"email": e, "kind": "job_posting", "source_url": src, "on_site": False, "where": label})
    return {"contacts": rank_contacts(found),
            "checked": (["the job's own pages"] if fc_key and urls else []) + (["public LinkedIn posts"] if serp_key else [])}

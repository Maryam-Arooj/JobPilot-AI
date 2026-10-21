"""Shared company research: run once per company, save with sources, return an honest payload."""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..ai_agents.company_research_agent import CompanyResearchAgent
from ..models.companies import Company, CompanyResearch, CompanyResearchClaim, CompanyResearchSource
from ..models.jobs import Job

STATUS_MESSAGES = {
    "found": "",
    "not_researched": "Company research has not run yet.",
    "not_found": "No official website could be found for this company, so the email uses only your CV and the job.",
    "unavailable": "The company website could not be read right now, so the email uses only your CV and the job.",
}
RETRY_AFTER = timedelta(hours=6)   # a failed lookup is retried later; a good one is kept


def get_or_create_company(db: Session, job: Job) -> Company:
    name = (job.company or "").strip() or "Unknown company"
    comp = db.query(Company).filter(Company.name == name).first()
    if not comp:
        comp = Company(name=name)   # the website is found by research, never guessed
        db.add(comp)
        db.flush()
    return comp


def latest(db: Session, company_id: int) -> Optional[CompanyResearch]:
    return (db.query(CompanyResearch).filter(CompanyResearch.company_id == company_id)
            .order_by(CompanyResearch.id.desc()).first())


def _status(rec: CompanyResearch) -> str:
    s = rec.confidence_status or ""
    if not s.endswith("_v2"):
        return "not_researched"      # saved by an older version (its website match was too loose) -> research again
    s = s[:-3]
    return "found" if s == "from_official_website" else (s if s in STATUS_MESSAGES else "unverified")


def _fresh(rec: CompanyResearch) -> bool:
    if _status(rec) == "not_researched":
        return False
    if _status(rec) == "found":
        return True
    ts = rec.research_timestamp
    if ts is None:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - ts < RETRY_AFTER


def linkedin_facts(db: Session, job: Optional[Job]) -> Dict[str, str]:
    """Company website + recruiter that LinkedIn itself showed for this job (saved from the Apify job search)."""
    from ..models.jobs import JobSource
    out = {"company_website": "", "company_linkedin": "", "poster_name": "", "poster_title": "", "poster_url": ""}
    if not job:
        return out
    for src in db.query(JobSource).filter(JobSource.job_id == job.id).all():
        raw = src.raw_data or {}
        for k in out:
            if not out[k] and isinstance(raw.get(k), str):
                out[k] = raw[k].strip()
    return out


def research_and_save(db: Session, comp: Company, job_url: Optional[str] = None, force: bool = False,
                      trusted_website: Optional[str] = None) -> CompanyResearch:
    from ..providers.company_providers import site_is_company
    if trusted_website:
        pass                                   # the company's own LinkedIn page names this website
    elif comp.official_website and not site_is_company(comp.official_website, comp.name):
        comp.official_website = None          # saved by the old, loose matcher (e.g. cedar.money for Cedar Global Solutions)
        force = True
    rec = latest(db, comp.id)
    if rec and not force and _fresh(rec) and (rec.confidence_status or "").endswith("_v2"):
        return rec
    data = CompanyResearchAgent().research(comp.name, comp.official_website, job_url, trusted_website)
    comp.official_website = data.get("official_website") or None
    if data.get("industry"):
        comp.industry = data["industry"]
    rec = CompanyResearch(
        company_id=comp.id, overview=data.get("overview") or "",
        products_services=data.get("products_services") or [], technology_info=data.get("technology_info") or [],
        engineering_info="", mission_info=data.get("mission_info") or "", recent_news=[],
        careers_url=data.get("careers_url") or "", confidence_status=(data.get("confidence_status") or "not_found") + "_v2")
    db.add(rec)
    db.flush()
    for src in data.get("sources") or []:
        db.add(CompanyResearchSource(research_id=rec.id, source_url=src.get("source_url") or "",
                                     provider=src.get("provider") or "firecrawl", raw_data=src.get("raw_data") or {}))
    for c in data.get("claims") or []:
        db.add(CompanyResearchClaim(research_id=rec.id, claim_text=c.get("claim_text") or "",
                                    source_url=c.get("source_url") or "", fact_type=c.get("fact_type") or "other"))
    db.flush()
    return rec


def payload(db: Session, comp: Company, rec: Optional[CompanyResearch]) -> Dict[str, Any]:
    if rec is None:
        return {"company_id": comp.id, "company_name": comp.name, "official_website": comp.official_website,
                "status": "not_researched", "message": "Company research has not run yet.", "overview": "",
                "industry": comp.industry or "", "products_services": [], "technology_info": [], "mission_info": "",
                "careers_url": "", "sources": [], "claims": [], "confidence_status": "not_researched"}
    status = _status(rec)
    sources = db.query(CompanyResearchSource).filter(CompanyResearchSource.research_id == rec.id).all()
    claims = db.query(CompanyResearchClaim).filter(CompanyResearchClaim.research_id == rec.id).all()
    ok = status == "found"
    return {
        "company_id": comp.id, "company_name": comp.name, "official_website": comp.official_website,
        "status": status, "message": STATUS_MESSAGES.get(status, "This research was saved by an older version and is not verified."),
        "overview": rec.overview if ok else "", "industry": comp.industry or "",
        "products_services": rec.products_services if ok else [], "technology_info": rec.technology_info if ok else [],
        "engineering_info": "", "mission_info": rec.mission_info if ok else "", "recent_news": [],
        "careers_url": rec.careers_url or "", "confidence_status": rec.confidence_status,
        "research_timestamp": rec.research_timestamp,
        "sources": [{"source_url": s.source_url, "provider": s.provider} for s in sources if s.provider != "contact_emails"],
        "claims": [{"claim_text": c.claim_text, "source_url": c.source_url, "fact_type": c.fact_type} for c in claims] if ok else [],
    }


CONTACTS_PROVIDER = "contact_emails"
CONTACTS_VERSION = 6


def cached_contacts(db: Session, comp: Optional[Company]) -> Optional[list]:
    if not comp:
        return None
    row = (db.query(CompanyResearchSource).join(CompanyResearch, CompanyResearch.id == CompanyResearchSource.research_id)
           .filter(CompanyResearch.company_id == comp.id, CompanyResearchSource.provider == CONTACTS_PROVIDER)
           .order_by(CompanyResearchSource.id.desc()).first())
    if not row or (row.raw_data or {}).get("v") != CONTACTS_VERSION:
        return None          # never searched, or searched by an older, weaker finder
    from ..providers.company_providers import rank_contacts
    return rank_contacts((row.raw_data or {}).get("contacts", []))


def find_contacts(db: Session, comp: Company, job_url: Optional[str] = None, force: bool = False,
                  trusted_website: Optional[str] = None) -> Dict[str, Any]:
    """Real recipient addresses for a company (cached). Never guesses an address."""
    from ..providers.company_providers import find_contact_emails
    cached = None if force else cached_contacts(db, comp)
    if cached is not None:
        return {"contacts": cached, "cached": True,
                "message": "" if cached else f"No public contact email for {comp.name} was found earlier."}
    from ..providers.company_providers import FirecrawlCompanyResearchProvider
    if trusted_website:
        from ..providers.company_providers import _root
        comp.official_website = _root(trusted_website)
    if not comp.official_website:                        # only the website is needed, not the full research
        try:
            site, _how = FirecrawlCompanyResearchProvider().find_official_website(comp.name, job_url)
        except Exception:
            site = None
        if site:
            comp.official_website = site
    out = find_contact_emails(comp.name, comp.official_website)
    rec = latest(db, comp.id)
    if rec is None:                                      # a holder row so the contacts can be cached
        rec = CompanyResearch(company_id=comp.id, overview="", products_services=[], technology_info=[],
                              engineering_info="", mission_info="", recent_news=[], careers_url="",
                              confidence_status="not_researched")
        db.add(rec)
        db.flush()
    db.add(CompanyResearchSource(research_id=rec.id, source_url=comp.official_website or "",
                                 provider=CONTACTS_PROVIDER, raw_data={"contacts": out["contacts"], "v": CONTACTS_VERSION,
                                                                        "checked": out.get("checked", [])}))
    db.flush()
    return {**out, "cached": False}


def remember_contacts(db: Session, comp: Optional[Company], contacts: list) -> None:
    """Save the merged list (job pages + company) in the company's contact cache."""
    if not comp:
        return
    row = (db.query(CompanyResearchSource).join(CompanyResearch, CompanyResearch.id == CompanyResearchSource.research_id)
           .filter(CompanyResearch.company_id == comp.id, CompanyResearchSource.provider == CONTACTS_PROVIDER)
           .order_by(CompanyResearchSource.id.desc()).first())
    if row:
        row.raw_data = {**(row.raw_data or {}), "contacts": contacts, "v": CONTACTS_VERSION}

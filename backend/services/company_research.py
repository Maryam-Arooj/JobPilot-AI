"""Shared company research: run once per company, save with sources, return an honest payload."""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..ai_agents.company_research_agent import CompanyResearchAgent
from ..models.companies import Company, CompanyResearch, CompanyResearchClaim, CompanyResearchSource
from ..models.jobs import Job

STATUS_MESSAGES = {
    "found": "",
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
    return "found" if s in ("from_official_website",) else (s if s in STATUS_MESSAGES else "unverified")


def _fresh(rec: CompanyResearch) -> bool:
    if _status(rec) == "found":
        return True
    ts = rec.research_timestamp
    if ts is None:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - ts < RETRY_AFTER


def research_and_save(db: Session, comp: Company, job_url: Optional[str] = None, force: bool = False) -> CompanyResearch:
    rec = latest(db, comp.id)
    if rec and not force and _fresh(rec):
        return rec
    data = CompanyResearchAgent().research(comp.name, comp.official_website, job_url)
    if data.get("official_website"):
        comp.official_website = data["official_website"]
    if data.get("industry"):
        comp.industry = data["industry"]
    rec = CompanyResearch(
        company_id=comp.id, overview=data.get("overview") or "",
        products_services=data.get("products_services") or [], technology_info=data.get("technology_info") or [],
        engineering_info="", mission_info=data.get("mission_info") or "", recent_news=[],
        careers_url=data.get("careers_url") or "", confidence_status=data.get("confidence_status") or "not_found")
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


def cached_contacts(db: Session, comp: Optional[Company]) -> Optional[list]:
    if not comp:
        return None
    row = (db.query(CompanyResearchSource).join(CompanyResearch, CompanyResearch.id == CompanyResearchSource.research_id)
           .filter(CompanyResearch.company_id == comp.id, CompanyResearchSource.provider == CONTACTS_PROVIDER)
           .order_by(CompanyResearchSource.id.desc()).first())
    return (row.raw_data or {}).get("contacts", []) if row else None


def find_contacts(db: Session, comp: Company, job_url: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
    """Real recipient addresses for a company (cached). Never guesses an address."""
    from ..providers.company_providers import find_contact_emails
    cached = None if force else cached_contacts(db, comp)
    if cached is not None:
        return {"contacts": cached, "cached": True,
                "message": "" if cached else f"No public contact email for {comp.name} was found earlier."}
    rec = research_and_save(db, comp, job_url)          # makes sure the official website is known
    out = find_contact_emails(comp.name, comp.official_website)
    db.add(CompanyResearchSource(research_id=rec.id, source_url=comp.official_website or "",
                                 provider=CONTACTS_PROVIDER, raw_data={"contacts": out["contacts"]}))
    db.flush()
    return {**out, "cached": False}

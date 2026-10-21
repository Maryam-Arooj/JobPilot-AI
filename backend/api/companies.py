from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..models.companies import Company
from ..models.jobs import Job
from ..services import company_research as cr
from ..services.agent_runs import current_run, track_run
from ..services.auth_middleware import get_current_user_id

router = APIRouter(prefix="/companies", tags=["companies"])


def _company(db: Session, company_id: int) -> Company:
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


def _job_url(db: Session, comp: Company):
    job = db.query(Job).filter(Job.company == comp.name).order_by(Job.id.desc()).first()
    return (job.application_url or job.source_url) if job else None


def _trusted_site(db: Session, comp: Company):
    job = db.query(Job).filter(Job.company == comp.name).order_by(Job.id.desc()).first()
    return cr.linkedin_facts(db, job).get("company_website") or None


@router.post("/{company_id}/research")
def research_company(company_id: int, force: bool = True, user_id: int = Depends(get_current_user_id),
                     db: Session = Depends(get_db)):
    comp = _company(db, company_id)
    with track_run(user_id, "email", f"Research {comp.name}", input_summary={"company": comp.name}) as run:
        run.step("Find website, read it, summarise", 1, 1)
        rec = cr.research_and_save(db, comp, _job_url(db, comp), force=force, trusted_website=_trusted_site(db, comp))
        db.commit()
        out = cr.payload(db, comp, rec)
        run.set_output({"status": out["status"], "website": out["official_website"], "claims": len(out["claims"])})
        return out


@router.get("/{company_id}")
def get_company(company_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    c = _company(db, company_id)
    return {"id": c.id, "name": c.name, "official_website": c.official_website, "industry": c.industry or "",
            "headquarters": c.headquarters or ""}


@router.get("/{company_id}/research")
def get_company_research(company_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    """Returns saved research only; it never starts a paid lookup by itself (use POST for that)."""
    comp = _company(db, company_id)
    return cr.payload(db, comp, cr.latest(db, comp.id))

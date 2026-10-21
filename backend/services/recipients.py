"""Recipient emails for a job: the posting, the job's pages, public LinkedIn posts, the company (cached)."""
import contextvars
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..models.companies import Company
from ..models.jobs import Job
from . import company_research as cr
from .agent_runs import run_warn

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def contact_emails(job: Optional[Job]) -> List[str]:
    """Real contact addresses written in the job posting itself (never guessed)."""
    if not job:
        return []
    text = " ".join(str(x) for x in [job.description or "", *(job.requirements or [])])
    found = []
    for e in EMAIL_RE.findall(text):
        e = e.strip(".").lower()
        if e not in found and not e.endswith((".png", ".jpg")) and "example." not in e:
            found.append(e)
    return found[:3]


def linkedin_url(job: Optional[Job]) -> str:
    for u in ((job.application_url or ""), (job.source_url or "")) if job else ():
        if "linkedin.com" in u:
            return u
    return ""


def known_recipients(db: Session, jobs: List[Job]) -> Dict[int, List[str]]:
    """Emails already known for each job, WITHOUT any new network call (posting + saved company contacts)."""
    names = {(j.company or "").strip() for j in jobs}
    comps = {c.name: c for c in db.query(Company).filter(Company.name.in_(names)).all()} if names else {}
    cache: Dict[str, List[str]] = {}
    out: Dict[int, List[str]] = {}
    for j in jobs:
        name = (j.company or "").strip()
        if name not in cache:
            cache[name] = [c["email"] for c in (cr.cached_contacts(db, comps.get(name)) or [])] if comps.get(name) else []
        emails = contact_emails(j) + [e for e in cache[name] if e not in contact_emails(j)]
        out[j.id] = emails[:3]
    return out


def search_recipients(db: Session, job: Job, comp: Optional[Company], force: bool = False) -> Dict[str, Any]:
    from ..providers.company_providers import find_job_contact_emails
    posting = [{"email": e, "kind": "job_posting", "source_url": job.application_url or job.source_url or "",
                "on_site": False} for e in contact_emails(job)]
    li = cr.linkedin_facts(db, job)
    recruiter = ({"name": li.get("poster_name"), "title": li.get("poster_title"), "profile_url": li.get("poster_url")}
                 if li.get("poster_name") else None)
    base = {"linkedin_url": linkedin_url(job), "recruiter": recruiter}
    if posting and not force:
        return {**base, "contacts": posting, "recipient": posting[0]["email"], "message": "", "checked": ["the job posting"]}
    cached = None if force else cr.cached_contacts(db, comp)
    with ThreadPoolExecutor(max_workers=1) as pool:
        job_future = None
        if not cached:   # the job's own pages + public LinkedIn posts, at the same time as the company search
            job_future = pool.submit(contextvars.copy_context().run, find_job_contact_emails, job.title or "",
                                     comp.name if comp else (job.company or ""),
                                     [u for u in {(job.application_url or ""), (job.source_url or "")} if u])
        found = cr.find_contacts(db, comp, job.application_url or job.source_url, force=force,
                                 trusted_website=li.get("company_website") or None) if comp \
            else {"contacts": [], "message": "This job has no company.", "checked": []}
        job_found = {"contacts": [], "checked": []}
        if job_future:
            try:
                job_found = job_future.result(timeout=45)
            except Exception as e:
                run_warn(f"Job-page recipient search failed: {e}")
    db.commit()
    seen = {p["email"] for p in posting}
    contacts = posting[:]
    for c in job_found["contacts"] + found["contacts"]:
        if c["email"] not in seen:
            seen.add(c["email"]); contacts.append(c)
    if job_found["contacts"]:
        cr.remember_contacts(db, comp, [c for c in contacts if c not in posting])
        db.commit()
    return {**base, "contacts": contacts, "recipient": contacts[0]["email"] if contacts else "",
            "checked": job_found.get("checked", []) + found.get("checked", []), "cached": found.get("cached"),
            "message": "" if contacts else found.get("message", "")}


# ---- batch: find recipient emails for many jobs in the background -------------------------------
import threading
import time
import uuid

_TASKS: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()


def start_batch(user_id: int, job_ids: List[int]) -> str:
    task_id = uuid.uuid4().hex[:12]
    with _LOCK:
        _TASKS[task_id] = {"user_id": user_id, "status": "running", "total": 0, "done": 0, "found": {},
                           "started": time.time(), "error": None}
    threading.Thread(target=_run_batch, args=(task_id, user_id, job_ids), daemon=True).start()
    return task_id


def get_batch(task_id: str, user_id: int) -> Optional[Dict[str, Any]]:
    t = _TASKS.get(task_id)
    if not t or t["user_id"] != user_id:
        return None
    return {k: v for k, v in t.items() if k != "user_id"}


def _run_batch(task_id: str, user_id: int, job_ids: List[int]) -> None:
    from ..db.database import SessionLocal
    from .agent_runs import track_run
    task = _TASKS[task_id]
    db = SessionLocal()
    try:
        jobs = db.query(Job).filter(Job.id.in_(job_ids)).all()
        by_company: Dict[str, List[Job]] = {}
        for j in jobs:
            by_company.setdefault((j.company or "").strip(), []).append(j)
        task["total"] = len(by_company)
        with track_run(user_id, "email", f"Find recruiter emails for {len(by_company)} companies",
                       input_summary={"jobs": len(jobs), "companies": len(by_company)}) as run:

            def one(company: str) -> None:
                s = SessionLocal()
                try:
                    group = s.query(Job).filter(Job.id.in_([j.id for j in by_company[company]])).all()
                    first = group[0]
                    comp = cr.get_or_create_company(s, first)
                    s.commit()
                    out = search_recipients(s, first, comp)
                    company_emails = [c["email"] for c in out["contacts"]]
                    for j in group:
                        emails = contact_emails(j) + [e for e in company_emails if e not in contact_emails(j)]
                        with _LOCK:
                            task["found"][j.id] = emails[:3]
                except Exception as e:
                    run_warn(f"Email search for {company} failed: {e}")
                finally:
                    s.close()
                    with _LOCK:
                        task["done"] += 1

            with ThreadPoolExecutor(max_workers=3) as pool:
                list(pool.map(lambda c: contextvars.copy_context().run(one, c), list(by_company)))
            with_email = sum(1 for v in task["found"].values() if v)
            run.set_output({"companies": len(by_company), "jobs_with_email": with_email, "jobs": len(jobs)})
        task["status"] = "done"
    except Exception as e:
        task["status"], task["error"] = "failed", str(e)[:200]
    finally:
        db.close()

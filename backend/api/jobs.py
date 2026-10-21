import logging
import re
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any, Set
from pydantic import BaseModel
from ..db.database import get_db
from ..models.jobs import Job, JobSource, JobRequirement, JobMatch, JobMatchEvidence, JobSearch
from ..models.applications import Application
from ..models.career_profile import CareerProfile
from ..services.auth_middleware import get_current_user_id
from ..ai_agents.job_discovery import JobDiscoveryAgent
from ..ai_agents.job_analysis import JobAnalysisAgent
from ..ai_agents.job_match import JobMatchAgent
from ..services.job_normalizer import normalize_job, deduplicate_jobs
from ..services.agent_runs import track_run
from ..services.locations import parse_location
from ..services.job_normalizer import clean_company
from ..services.job_matching import (analyze_job_with_ai, candidate_skills, candidate_title, job_text,
                                     required_years, score_job)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])

def _user_job_ids(db: Session, user_id: int) -> Set[int]:
    """Jobs this user surfaced via their own searches (ids kept in JobSearch.provider_status),
    plus jobs they have matched against or applied to."""
    ids: Set[int] = set()
    for (status,) in db.query(JobSearch.provider_status).filter(JobSearch.user_id == user_id).all():
        if isinstance(status, dict):
            ids.update(i for i in status.get("job_ids", []) if isinstance(i, int))
    ids.update(jid for (jid,) in db.query(JobMatch.job_id).filter(JobMatch.user_id == user_id).all())
    ids.update(jid for (jid,) in db.query(Application.job_id).filter(Application.user_id == user_id).all())
    return ids

def infer_country(location: str = "", existing_country: str = "") -> str:
    """Country from the job's own location text (stored values from older versions were sometimes wrong)."""
    from ..services.locations import country_of
    return country_of(location, existing_country if not (location or "").strip() else None)


def _profile_dict(profile: Optional[CareerProfile]) -> Dict[str, Any]:
    if not profile:
        return {}
    return {"personal": profile.personal or {}, "professional": profile.professional or {},
            "skills": profile.skills or {}, "experience": profile.experience or [], "education": profile.education or []}


def _job_payload(job: Job, scored: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    body = {
        "id": job.id, "title": job.title,
        "company": clean_company(job.company or "")[0] or "Company not disclosed",
        "listed_by": clean_company(job.company or "")[1],
        "location": parse_location(job.location or "")["display"] or (job.location or ""),
        "city": parse_location(job.location or "")["city"], "region": parse_location(job.location or "")["region"],
        "country": infer_country(job.location or "", job.country or ""), "remote": job.remote,
        "employment_type": job.employment_type, "salary": job.salary, "description": job.description,
        "requirements": job.requirements, "preferred_skills": job.preferred_skills,
        "responsibilities": job.responsibilities, "application_url": job.application_url,
        "technologies": job.technologies, "seniority": job.seniority, "industry": job.industry, "source": job.source,
    }
    if scored is not None:
        body.update({
            "match_score": scored["match_score"], "alignment": scored["alignment"],
            "badge": scored["alignment"], "matched_skills": scored["matched_skills"][:8],
            "missing_skills": scored["missing_skills"][:6], "gaps": scored["gaps"][:6],
            "recommendation": (
                "This job doesn't list skills we can compare with your CV — open it to read the details."
                if scored["match_score"] is None else
                f"Your CV covers {len(scored['matched_skills'])} of the {len(scored['matched_skills']) + len(scored['missing_skills'])} skills this job mentions"
                + (f"; missing: {', '.join(scored['missing_skills'][:3])}." if scored["missing_skills"] else ".")),
        })
    return body


def _save_jobs(db: Session, user_id: int, query: str, intent: Dict[str, Any], jobs: List[Dict[str, Any]]) -> List[Job]:
    search_record = JobSearch(user_id=user_id, natural_language_query=query, structured_intent=intent,
                              results_count=len(jobs))
    db.add(search_record)
    db.flush()
    saved: List[Job] = []
    for j in jobs:
        c_url = j.get("canonical_application_url") or j.get("application_url")
        existing = db.query(Job).filter(Job.application_url == c_url).first() if c_url else None
        if existing is None:
            existing = (db.query(Job).filter(Job.normalized_title == j["normalized_title"],
                                             Job.normalized_company == j["normalized_company"],
                                             Job.location == (j.get("location") or "")).first())
        if existing is not None:
            if j.get("remote") and not existing.remote:
                existing.remote = True  # found again by a remote / work-from-home search
            # keep LinkedIn's company website / recruiter for jobs saved before we stored them
            for src in j.get("sources", []):
                raw = src.get("raw_data") or {}
                if raw.get("company_website") or raw.get("poster_name"):
                    have = db.query(JobSource).filter(JobSource.job_id == existing.id,
                                                      JobSource.provider == src.get("provider", "search")).all()
                    if not any((h.raw_data or {}).get("company_website") or (h.raw_data or {}).get("poster_name") for h in have):
                        db.add(JobSource(job_id=existing.id, provider=src.get("provider", "search"),
                                         source_url=src.get("source_url", ""), raw_data=raw))
            saved.append(existing)
            continue
        job = Job(
            title=j["title"], company=j["company"], location=j.get("location") or "", remote=bool(j.get("remote")),
            employment_type=j.get("employment_type"), salary=j.get("salary"), description=j.get("description", ""),
            requirements=j.get("requirements", []), preferred_skills=j.get("preferred_skills", []),
            responsibilities=j.get("responsibilities", []), application_url=c_url or "",
            source=j.get("source"), source_url=j.get("source_url", ""), extraction_method=j.get("extraction_method", "provider"),
            technologies=j.get("technologies", []), seniority=j.get("seniority"), experience_years=j.get("experience_years"),
            industry=j.get("industry"), job_type=j.get("job_type"),
            country=infer_country(j.get("location", ""), j.get("country", "")), city=j.get("city", ""),
            normalized_title=j.get("normalized_title", ""), normalized_company=j.get("normalized_company", ""),
        )
        db.add(job)
        db.flush()
        for src in j.get("sources", []):
            db.add(JobSource(job_id=job.id, provider=src.get("provider", "search"), source_url=src.get("source_url", ""),
                             raw_data=src.get("raw_data", {})))
        saved.append(job)
    search_record.provider_status = {"job_ids": [j.id for j in saved]}
    db.commit()
    return saved


REMOTE_WORDS = ("remote worldwide", "remote", "worldwide remote", "work from home")


def _discover(run, query: str, searches: List[Dict[str, Any]], profile_data: Dict[str, Any]) -> Dict[str, Any]:
    """Run one or more live searches (e.g. remote + a country) in parallel and merge them."""
    import contextvars
    from concurrent.futures import ThreadPoolExecutor
    label = " + ".join("remote" if s.get("remote") else (s.get("location") or "any location") for s in searches)
    run.step(f"Search live jobs on Google Jobs + LinkedIn ({label})", 1, 3)
    ctx = contextvars.copy_context()
    outcomes = []
    with ThreadPoolExecutor(max_workers=len(searches)) as pool:
        futs = [pool.submit(ctx.copy().run, JobDiscoveryAgent().discover, query, profile_data,
                            s.get("location"), bool(s.get("remote"))) for s in searches]
        for s, f in zip(searches, futs):
            try:
                outcomes.append((s, f.result()))
            except HTTPException as e:
                logger.error("Job discovery failed for %s: %s", s, e.detail)
                outcomes.append((s, None))
    ok = [(s, r) for s, r in outcomes if r is not None]
    if not ok:
        raise HTTPException(status_code=503,
                            detail="No jobs returned from live job providers. Check Agent Transparency for each provider's error.")
    from ..services.job_normalizer import deduplicate_jobs
    merged, errors, status = [], [], {}
    for s, r in ok:
        tag = "remote" if s.get("remote") else (s.get("location") or "any")
        for j in r["results"]:
            if s.get("remote"):
                j["remote"] = j.get("remote") or True
            merged.append(j)
        errors += r["provider_errors"]
        for name, st in r["provider_status"].items():
            status[f"{name} [{tag}]"] = st
    return {"intent": ok[0][1]["intent"], "results": deduplicate_jobs(merged), "provider_errors": errors, "provider_status": status}


def _searches_for(location: Optional[str], mode: str = "auto") -> List[Dict[str, Any]]:
    """mode: auto = remote first + the location (if any); remote = remote only; location = that place only."""
    loc = (location or "").strip()
    if loc.lower() in REMOTE_WORDS or mode == "remote":
        return [{"remote": True}]
    if mode == "location":
        return [{"location": loc or None}]
    return [{"remote": True}] + ([{"location": loc}] if loc and loc.upper() != "ALL" else [])


def _rank(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Best match first; remote jobs get a small preference within similar scores."""
    return sorted(results, key=lambda r: (r.get("match_score") is None,
                                          -((r.get("match_score") or 0) + (5 if r.get("remote") else 0))))


@router.post("/search")
def search_jobs(
    query: str = Query(..., description="Job title / keywords"),
    country: Optional[str] = Query(None, description="Country or city, 'Remote Worldwide', or ALL"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    location = country if country and country.upper() != "ALL" else None
    searches = _searches_for(location, "remote" if (location or "").lower() in REMOTE_WORDS else "location")
    with track_run(user_id, "job", f"Search jobs: {query}" + (f" ({location})" if location else ""),
                   input_summary={"query": query, "location": location}) as run:
        profile = _profile_dict(db.query(CareerProfile).filter(CareerProfile.user_id == user_id).first())
        res = _discover(run, query, searches, profile)
        run.step("Save and score jobs against your CV", 3, 3)
        saved = _save_jobs(db, user_id, query, res["intent"], res["results"])
        results = _rank([_job_payload(j, score_job(profile, _job_dict(j)) if profile else None) for j in saved])
        if res["provider_errors"]:
            run.warn(f"{len(res['provider_errors'])} provider call(s) failed; results come from the others")
        if not saved:
            run.warn("The live providers returned no jobs for this search")
        run.set_output({"jobs": len(saved), "providers": res["provider_status"]})
        return {"intent": res["intent"], "results": results, "provider_status": res["provider_status"]}


class FromCvRequest(BaseModel):
    profile_data: Optional[Dict[str, Any]] = None   # from /documents/parse (works without saving the CV)
    query: Optional[str] = None                      # override the role taken from the CV
    location: Optional[str] = None                   # override the location taken from the CV
    mode: str = "auto"                               # auto = remote + location, remote, location


def cv_search_terms(profile: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Role + location for a job search, taken from the CV itself."""
    role = candidate_title(profile)
    role = re.split(r"\s*[|&/,]\s*|\s+and\s+", role)[0].strip() if role else ""
    if not role:
        skills = candidate_skills(profile)
        role = f"{skills[0]} developer" if skills else ""
    loc = ((profile.get("personal") or {}).get("location") or "").strip() or None
    return {"query": role or None, "location": loc}


@router.post("/from-cv")
def jobs_from_cv(req: FromCvRequest, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    """Upload-your-CV quick path: search live jobs for the CV's role and location and rank them by match."""
    profile = req.profile_data or _profile_dict(db.query(CareerProfile).filter(CareerProfile.user_id == user_id).first())
    if not profile or not (candidate_title(profile) or candidate_skills(profile)):
        raise HTTPException(status_code=400, detail="Upload your CV first: no job title or skills were found to search with.")
    terms = cv_search_terms(profile)
    query = (req.query or terms["query"] or "").strip()
    location = (req.location or terms["location"] or "").strip() or None
    if location and location.upper() == "ALL":
        location = terms["location"]
    searches = _searches_for(location, req.mode if req.mode in ("auto", "remote", "location") else "auto")
    where = " + ".join("remote" if s.get("remote") else (s.get("location") or "any location") for s in searches)
    with track_run(user_id, "job", f"Find jobs for your CV: {query} ({where})",
                   input_summary={"query": query, "location": location, "mode": req.mode, "skills": len(candidate_skills(profile)),
                                  "source": "uploaded CV" if req.profile_data else "saved profile"}) as run:
        res = _discover(run, query, searches, profile)
        run.step("Rank jobs by match with your CV (remote preferred)", 3, 3)
        saved = _save_jobs(db, user_id, f"[CV] {query}", res["intent"], res["results"])
        ranked = _rank([_job_payload(j, score_job(profile, _job_dict(j))) for j in saved])
        run.set_output({"query": query, "searched": where, "jobs": len(ranked),
                        "remote_jobs": sum(1 for r in ranked if r.get("remote")),
                        "top": [f"{r['title']} @ {r['company']} ({r['match_score']})" for r in ranked[:3]],
                        "providers": res["provider_status"]})
        if not ranked:
            run.warn("The live providers returned no jobs for this role and location")
        return {"query": query, "location": location, "searched": where, "candidate_skills": candidate_skills(profile),
                "results": ranked, "provider_status": res["provider_status"]}


def _job_dict(j: Job) -> Dict[str, Any]:
    return {"title": j.title, "description": j.description, "requirements": j.requirements,
            "preferred_skills": j.preferred_skills, "responsibilities": j.responsibilities, "technologies": j.technologies}


@router.get("/recommendations")
def get_job_recommendations(limit: int = 20, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    """Your jobs ranked by honest match with your profile (no invented scores)."""
    profile = _profile_dict(db.query(CareerProfile).filter(CareerProfile.user_id == user_id).first())
    allowed_ids = _user_job_ids(db, user_id)
    jobs = db.query(Job).filter(Job.id.in_(allowed_ids)).order_by(Job.id.desc()).limit(100).all() if allowed_ids else []
    recs = _rank([_job_payload(j, score_job(profile, _job_dict(j))) for j in jobs])
    return {"candidate_skills": candidate_skills(profile), "total_recommendations": len(recs), "results": recs[:limit]}


@router.get("/")
def list_jobs(
    remote: Optional[bool] = None,
    query: Optional[str] = None,
    country: Optional[str] = None,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    allowed_ids = _user_job_ids(db, user_id)
    if not allowed_ids:
        return []
    q = db.query(Job).filter(Job.id.in_(allowed_ids))
    if remote is not None:
        q = q.filter(Job.remote == remote)
    if query:
        search_pattern = f"%{query.lower()}%"
        q = q.filter(
            (Job.normalized_title.like(search_pattern)) | 
            (Job.normalized_company.like(search_pattern)) |
            (Job.location.ilike(search_pattern))
        )
    jobs = q.order_by(Job.id.desc()).all()
    
    res = []
    for j in jobs:
        c_name = infer_country(j.location, j.country)
        if country and country.upper() != "ALL":
            if country.strip().lower() != c_name.lower():
                continue

        match = db.query(JobMatch).filter(JobMatch.user_id == user_id, JobMatch.job_id == j.id).first()
        res.append({
            "id": j.id,
            "title": j.title,
            "company": clean_company(j.company or "")[0] or "Company not disclosed",
            "listed_by": clean_company(j.company or "")[1],
            "location": parse_location(j.location or "")["display"] or (j.location or ""),
            "country": c_name,
            "remote": j.remote,
            "employment_type": j.employment_type,
            "salary": j.salary,
            "description": j.description,
            "requirements": j.requirements,
            "preferred_skills": j.preferred_skills,
            "responsibilities": j.responsibilities,
            "technologies": j.technologies,
            "seniority": j.seniority,
            "application_url": j.application_url,
            "alignment": match.overall_alignment if match else "Unmatched"
        })
    return res


@router.get("/{job_id}")
def get_job(job_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    match = db.query(JobMatch).filter(JobMatch.user_id == user_id, JobMatch.job_id == job_id).order_by(JobMatch.id.desc()).first()
    evidence_list = []
    if match:
        ev_records = db.query(JobMatchEvidence).filter(JobMatchEvidence.match_id == match.id).all()
        evidence_list = [
            {
                "evidence_type": ev.evidence_type,
                "career_profile_fact_path": ev.career_profile_fact_path,
                "job_requirement_text": ev.job_requirement_text,
                "explanation": ev.explanation
            } for ev in ev_records
        ]
        
    return {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "remote": job.remote,
        "employment_type": job.employment_type,
        "salary": job.salary,
        "description": job.description,
        "requirements": job.requirements,
        "preferred_skills": job.preferred_skills,
        "responsibilities": job.responsibilities,
        "application_url": job.application_url,
        "source": job.source,
        "source_url": job.source_url,
        "technologies": job.technologies,
        "seniority": job.seniority,
        "experience_years": job.experience_years,
        "industry": job.industry,
        "match": {
            "overall_alignment": match.overall_alignment,
            "skills_match": match.skills_match,
            "experience_match": match.experience_match,
            "matched_requirements": match.matched_requirements,
            "gaps": match.gaps,
            "evidence": evidence_list
        } if match else None
    }

@router.post("/{job_id}/analyze")
def analyze_job(job_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    with track_run(user_id, "job", f"Analyse job #{job_id}: {job.title}", input_summary={"job_id": job_id}) as run:
        ai = analyze_job_with_ai(_job_dict(job))
        run.set_output({"ai": ai is not None})
        return ai or {"required_skills": score_job({}, _job_dict(job))["missing_skills"], "preferred_skills": [],
                      "min_years": required_years(job_text(_job_dict(job))), "education": None, "seniority": job.seniority,
                      "method": "keywords"}


@router.post("/{job_id}/match")
def match_job(job_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    with track_run(user_id, "job", f"Match profile to job #{job_id}: {job.title}", input_summary={"job_id": job_id}) as run:
        profile = _profile_dict(db.query(CareerProfile).filter(CareerProfile.user_id == user_id).first())
        run.step("AI reads the job requirements (grounded in the job text)", 1, 3)
        ai = analyze_job_with_ai(_job_dict(job))
        run.step("Compare with your CV", 2, 3)
        skills = (ai["required_skills"] + ai["preferred_skills"]) if ai and (ai["required_skills"] or ai["preferred_skills"]) else None
        scored = score_job(profile, _job_dict(job), job_skills=skills)
        run.step("Save match evidence", 3, 3)
        record = JobMatch(user_id=user_id, job_id=job_id, overall_alignment=scored["alignment"],
                          skills_match={"matched": scored["matched_skills"], "gaps": scored["missing_skills"],
                                        "score": scored["match_score"], "method": "ai" if skills else "keywords"},
                          experience_match={"required_years": scored["required_years"], "verified_years": scored["candidate_years"]},
                          education_match={"required": (ai or {}).get("education"), "matched": None},
                          location_match={"job_location": job.location, "remote": job.remote},
                          responsibility_match={}, matched_requirements=scored["matched_skills"], gaps=scored["gaps"])
        db.add(record)
        db.flush()
        for ev in scored["evidence"]:
            db.add(JobMatchEvidence(match_id=record.id, evidence_type=ev["type"],
                                    career_profile_fact_path=ev["career_profile_fact_path"],
                                    job_requirement_text=ev["job_requirement_text"], explanation=ev["explanation"]))
        db.commit()
        run.set_output({"job": f"{job.title} at {job.company}", "score": scored["match_score"], "alignment": scored["alignment"],
                        "method": "ai" if skills else "keywords", "matched": len(scored["matched_skills"]), "gaps": len(scored["gaps"])})
        return {"overall_alignment": scored["alignment"], "match_score": scored["match_score"],
                "skills_match": {"matched": scored["matched_skills"], "gaps": scored["missing_skills"]},
                "experience_match": {"required_years": scored["required_years"], "verified_years": scored["candidate_years"]},
                "education_match": {"required": (ai or {}).get("education")},
                "matched_requirements": scored["matched_skills"], "gaps": scored["gaps"], "evidence": scored["evidence"],
                "method": "ai" if skills else "keywords"}


@router.get("/{job_id}/sources")
def get_job_sources(job_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    sources = db.query(JobSource).filter(JobSource.job_id == job_id).all()
    return [
        {
            "id": s.id,
            "provider": s.provider,
            "source_url": s.source_url,
            "retrieved_at": s.retrieved_at,
            "raw_data": s.raw_data
        } for s in sources
    ]

@router.get("/{job_id}/match")
def get_job_match(job_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    match = db.query(JobMatch).filter(JobMatch.user_id == user_id, JobMatch.job_id == job_id).order_by(JobMatch.id.desc()).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match evaluation not found for this job")
    ev_records = db.query(JobMatchEvidence).filter(JobMatchEvidence.match_id == match.id).all()
    return {
        "overall_alignment": match.overall_alignment,
        "skills_match": match.skills_match,
        "experience_match": match.experience_match,
        "matched_requirements": match.matched_requirements,
        "gaps": match.gaps,
        "evidence": [
            {
                "evidence_type": ev.evidence_type,
                "career_profile_fact_path": ev.career_profile_fact_path,
                "job_requirement_text": ev.job_requirement_text,
                "explanation": ev.explanation
            } for ev in ev_records
        ]
    }


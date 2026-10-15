import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any, Set
from ..db.database import get_db
from ..models.jobs import Job, JobSource, JobRequirement, JobMatch, JobMatchEvidence, JobSearch
from ..models.applications import Application
from ..models.career_profile import CareerProfile
from ..services.auth_middleware import get_current_user_id
from ..ai_agents.job_discovery import JobDiscoveryAgent
from ..ai_agents.job_analysis import JobAnalysisAgent
from ..ai_agents.job_match import JobMatchAgent
from ..services.job_normalizer import normalize_job, deduplicate_jobs

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
    if existing_country and len(existing_country.strip()) > 1:
        return existing_country.strip()
    loc = (location or "").lower()
    if "pakistan" in loc or "lahore" in loc or "karachi" in loc or "islamabad" in loc or "rawalpindi" in loc:
        return "Pakistan"
    if "united states" in loc or "usa" in loc or "us " in loc or ", ca" in loc or ", ny" in loc or ", tx" in loc or ", wa" in loc or "jersey city" in loc:
        return "United States"
    if "united kingdom" in loc or "uk" in loc or "london" in loc or "england" in loc:
        return "United Kingdom"
    if "canada" in loc or "toronto" in loc or "vancouver" in loc:
        return "Canada"
    if "uae" in loc or "dubai" in loc or "abu dhabi" in loc or "emirates" in loc:
        return "United Arab Emirates"
    if "germany" in loc or "berlin" in loc or "munich" in loc:
        return "Germany"
    if "remote" in loc:
        return "Remote Worldwide"
    return "Global / Unspecified"

@router.post("/search")
def search_jobs(
    query: str = Query(..., description="Natural language job search query"),
    country: Optional[str] = Query(None, description="Country filter"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    profile = db.query(CareerProfile).filter(CareerProfile.user_id == user_id).first()
    profile_data = {
        "professional": profile.professional or {} if profile else {},
        "skills": profile.skills or {} if profile else {},
        "experience": profile.experience or [] if profile else [],
        "education": profile.education or [] if profile else []
    }
    
    agent = JobDiscoveryAgent()
    discovery_query = f"{query} in {country}" if country and country.upper() != "ALL" else query
    try:
        discovery_res = agent.discover(discovery_query, profile_data)
    except HTTPException as e:
        # Provider errors can embed request URLs/tokens; keep them in server logs only.
        logger.error("Job discovery failed: %s", e.detail)
        raise HTTPException(
            status_code=e.status_code,
            detail="No jobs returned from live job providers. Check server logs for provider status."
        )
    intent = discovery_res.get("intent", {})
    deduped_jobs = discovery_res.get("results", [])
    
    search_record = JobSearch(
        user_id=user_id,
        natural_language_query=query,
        structured_intent=intent,
        results_count=len(deduped_jobs)
    )
    db.add(search_record)
    db.commit()

    saved_jobs = []
    for j_data in deduped_jobs:
        c_url = j_data.get("canonical_application_url") or j_data.get("application_url")
        existing_job = None
        if c_url:
            existing_job = db.query(Job).filter(Job.application_url == c_url).first()
            
        if existing_job:
            job_obj = existing_job
        else:
            inferred_c = infer_country(j_data.get("location", ""), j_data.get("country", ""))
            job_obj = Job(
                title=j_data.get("title") or "Untitled Position",
                company=j_data.get("company") or "Unknown Company",
                location=j_data.get("location") or "Remote / Flexible",
                remote=bool(j_data.get("remote")),
                employment_type=j_data.get("employment_type", "Full-time"),
                salary=j_data.get("salary"),
                description=j_data.get("description", ""),
                requirements=j_data.get("requirements", []),
                preferred_skills=j_data.get("preferred_skills", []),
                responsibilities=j_data.get("responsibilities", []),
                application_url=c_url or j_data.get("application_url", ""),
                source=j_data.get("source", "apify/serp"),
                source_url=j_data.get("source_url", ""),
                extraction_method=j_data.get("extraction_method", "provider"),
                technologies=j_data.get("technologies", []),
                seniority=j_data.get("seniority", "Mid-Senior"),
                experience_years=j_data.get("experience_years"),
                industry=j_data.get("industry", "Technology"),
                job_type=j_data.get("job_type", "Full-time"),
                country=inferred_c,
                city=j_data.get("city", ""),
                normalized_title=j_data.get("normalized_title", ""),
                normalized_company=j_data.get("normalized_company", "")
            )
            db.add(job_obj)
            db.flush()
            
            for src in j_data.get("sources", []):
                db.add(JobSource(
                    job_id=job_obj.id,
                    provider=src.get("provider", "search"),
                    source_url=src.get("source_url", ""),
                    raw_data=src.get("raw_data", {})
                ))
            db.commit()

        saved_jobs.append({
            "id": job_obj.id,
            "title": job_obj.title,
            "company": job_obj.company,
            "location": job_obj.location,
            "country": infer_country(job_obj.location, job_obj.country),
            "remote": job_obj.remote,
            "employment_type": job_obj.employment_type,
            "salary": job_obj.salary,
            "description": job_obj.description,
            "requirements": job_obj.requirements,
            "preferred_skills": job_obj.preferred_skills,
            "responsibilities": job_obj.responsibilities,
            "application_url": job_obj.application_url,
            "technologies": job_obj.technologies,
            "seniority": job_obj.seniority,
            "industry": job_obj.industry,
            "source": job_obj.source
        })

    search_record.provider_status = {"job_ids": [j["id"] for j in saved_jobs]}
    db.commit()

    return {"intent": intent, "results": saved_jobs}

@router.get("/recommendations")
def get_job_recommendations(
    limit: int = 20,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Find jobs and generate personalized recommendations tailored to candidate's CV & career profile.
    """
    profile = db.query(CareerProfile).filter(CareerProfile.user_id == user_id).first()
    
    # Extract user skills
    user_skills = []
    if profile and profile.skills:
        if isinstance(profile.skills, dict):
            for v in profile.skills.values():
                if isinstance(v, list):
                    user_skills.extend([str(s) for s in v if s])
                elif isinstance(v, str):
                    user_skills.append(v)
        elif isinstance(profile.skills, list):
            user_skills = [str(s) for s in profile.skills if s]

    if profile and profile.professional and isinstance(profile.professional, dict):
        prof_skills = profile.professional.get("skills", [])
        if isinstance(prof_skills, list):
            user_skills.extend([str(s) for s in prof_skills if s])

    # Deduplicate preserving order
    user_skills = list(dict.fromkeys(user_skills))
    user_skills_lower = [s.lower().strip() for s in user_skills]

    allowed_ids = _user_job_ids(db, user_id)
    jobs = db.query(Job).filter(Job.id.in_(allowed_ids)).order_by(Job.id.desc()).limit(100).all() if allowed_ids else []

    recommendations = []
    for j in jobs:
        reqs = [str(r).lower() for r in (j.requirements or [])]
        techs = [str(t).lower() for t in (j.technologies or [])]
        prefs = [str(p).lower() for p in (j.preferred_skills or [])]
        all_job_skills = list(set(reqs + techs + prefs))

        matched = []
        missing = []
        for sk in all_job_skills:
            if any(us in sk or sk in us for us in user_skills_lower):
                matched.append(sk.title())
            else:
                missing.append(sk.title())

        # If job has no explicit skills array, scan description for user skills
        if not matched and user_skills:
            desc_lower = (j.description or "").lower()
            for us in user_skills:
                if us.lower() in desc_lower:
                    matched.append(us)

        if all_job_skills:
            base_ratio = len(matched) / len(all_job_skills)
            score = max(40, int(base_ratio * 100))
        elif matched:
            score = min(95, 60 + len(matched) * 10)
        else:
            score = 75 if user_skills else 70

        if profile and profile.professional:
            headline = str(profile.professional.get("headline", "")).lower()
            if headline and any(w in j.title.lower() for w in headline.split() if len(w) > 3):
                score = min(98, score + 12)

        if score >= 85:
            alignment = "Strong Alignment"
            badge = "Top Match"
        elif score >= 65:
            alignment = "Good Fit"
            badge = "Competitive"
        else:
            alignment = "Growth Opportunity"
            badge = "Skill Gap"

        if matched:
            rec_text = f"High alignment with your verified skills in {', '.join(matched[:3])}. Direct match with target engineering competencies."
        else:
            rec_text = f"Good target for expanding into {', '.join(missing[:2]) if missing else 'adjacent technical stacks'}."

        recommendations.append({
            "id": j.id,
            "title": j.title,
            "company": j.company,
            "location": j.location,
            "country": infer_country(j.location, j.country),
            "remote": j.remote,
            "employment_type": j.employment_type,
            "salary": j.salary,
            "description": j.description,
            "application_url": j.application_url,
            "match_score": score,
            "alignment": alignment,
            "badge": badge,
            "matched_skills": matched[:5],
            "missing_skills": missing[:4],
            "recommendation": rec_text,
            "technologies": j.technologies
        })

    recommendations.sort(key=lambda x: x["match_score"], reverse=True)

    return {
        "candidate_skills": user_skills,
        "total_recommendations": len(recommendations),
        "results": recommendations[:limit]
    }

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
            if country.lower() not in c_name.lower() and country.lower() not in j.location.lower():
                continue

        match = db.query(JobMatch).filter(JobMatch.user_id == user_id, JobMatch.job_id == j.id).first()
        res.append({
            "id": j.id,
            "title": j.title,
            "company": j.company,
            "location": j.location,
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
    agent = JobAnalysisAgent()
    analysis = agent.analyze({
        "title": job.title,
        "company": job.company,
        "description": job.description,
        "requirements": job.requirements,
        "preferred_skills": job.preferred_skills,
        "location": job.location,
        "remote": job.remote,
        "responsibilities": job.responsibilities,
        "technologies": job.technologies,
        "seniority": job.seniority,
        "industry": job.industry
    })
    return analysis

@router.post("/{job_id}/match")
def match_job(job_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    profile = db.query(CareerProfile).filter(CareerProfile.user_id == user_id).first()
    profile_dict = {
        "skills": profile.skills or {} if profile else {},
        "experience": profile.experience or [] if profile else [],
        "education": profile.education or [] if profile else [],
        "professional": profile.professional or {} if profile else {}
    }
    
    analysis_agent = JobAnalysisAgent()
    analysis = analysis_agent.analyze({
        "title": job.title,
        "company": job.company,
        "description": job.description,
        "requirements": job.requirements,
        "preferred_skills": job.preferred_skills,
        "responsibilities": job.responsibilities,
        "technologies": job.technologies,
        "experience_years": job.experience_years
    })
    
    match_agent = JobMatchAgent()
    match_res = match_agent.match(profile_dict, {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "remote": job.remote
    }, analysis)
    
    # Persist JobMatch & JobMatchEvidence
    match_record = JobMatch(
        user_id=user_id,
        job_id=job_id,
        overall_alignment=match_res["overall_alignment"],
        skills_match=match_res.get("skills_match", {}),
        experience_match=match_res.get("experience_match", {}),
        education_match=match_res.get("education_match", {}),
        location_match=match_res.get("location_match", {}),
        responsibility_match=match_res.get("responsibility_match", {}),
        matched_requirements=match_res.get("matched_requirements", []),
        gaps=match_res.get("gaps", [])
    )
    db.add(match_record)
    db.flush()
    
    for ev in match_res.get("evidence", []):
        db.add(JobMatchEvidence(
            match_id=match_record.id,
            evidence_type=ev.get("type", "match"),
            career_profile_fact_path=ev.get("career_profile_fact_path", "profile"),
            job_requirement_text=ev.get("job_requirement_text", ""),
            explanation=ev.get("explanation", "")
        ))
    db.commit()
    
    return match_res

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


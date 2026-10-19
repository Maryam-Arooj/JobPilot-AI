import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..ai_agents.profile_agent import flatten_skills, normalize_skills
from ..db.database import get_db
from ..models.career_profile import CareerProfile, ProfileFact
from ..services.agent_runs import track_run
from ..services.auth_middleware import get_current_user_id
from ..ai_agents.profile_agent import ProfileAgent
from ..services import cv_refine
from ..services.document_service import extract_text_and_profile, extract_text_from_file_bytes
from ..services.profile_ingest import (filter_confirmed_profile_data, get_or_create_profile,
                                       recompute_completeness, save_extraction)

router = APIRouter(prefix="/documents", tags=["documents"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class SyncProfileRequest(BaseModel):
    profile_data: Optional[Dict[str, Any]] = None
    facts: Optional[List[Dict[str, Any]]] = None


async def _read_upload(file: UploadFile) -> bytes:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="The file is larger than 10 MB.")
    return content


def _profile_payload(profile: CareerProfile) -> Dict[str, Any]:
    return {"personal": profile.personal, "professional": profile.professional, "skills": profile.skills,
            "experience": profile.experience, "education": profile.education,
            "certifications": profile.certifications, "projects": profile.projects}


def _read_text_tracked(content: bytes, filename: str) -> str:
    from ..services.agent_runs import tool_call, run_warn
    kind = (filename.rsplit(".", 1)[-1] if "." in filename else "text").lower()
    with tool_call(f"parser:{kind}", f"extract text from {filename}") as t:
        text = extract_text_from_file_bytes(content, filename)
        t["summary"] = f"{len(text)} characters of text extracted"
    if not text.strip():
        run_warn("No text could be extracted from the document.")
    return text


def _extraction_body(filename: str, text: str, extracted: Dict[str, Any], refine_job_id: Optional[str]) -> Dict[str, Any]:
    return {
        "filename": filename,
        "facts": extracted.get("facts", []),
        "profile_data": extracted.get("profile_data", {}),
        "text": text,
        "missing_fields": extracted.get("missing_fields", []),
        "followup_questions": extracted.get("followup_questions", []),
        "extraction_method": extracted.get("extraction_method"),
        "dropped": extracted.get("dropped", []),
        "message": extracted.get("message", ""),
        "refine_job_id": refine_job_id,
        "refining": refine_job_id is not None,
    }


@router.post("/parse")
async def parse_document(file: UploadFile = File(...), wait: bool = Query(False, description="true = wait for the AI result"),
                         user_id: int = Depends(get_current_user_id)):
    """Read a CV for review. Nothing is saved.

    Default: returns the instant quick read (text copied from the CV) in seconds and starts the AI
    refinement in the background (poll GET /documents/refine/{refine_job_id}). wait=true runs the AI
    extraction before answering.
    """
    filename = file.filename or "cv.pdf"
    with track_run(user_id, "cv", f"Read CV for review: {filename}",
                   input_summary={"filename": filename, "content_type": file.content_type, "wait": wait}) as run:
        run.step("Read document", 1, 2)
        content = await _read_upload(file)
        text = await run_in_threadpool(_read_text_tracked, content, filename)
        if wait:
            run.step("AI extraction and grounding check", 2, 2)
            extracted = await run_in_threadpool(ProfileAgent().extract_from_text, text)
            job_id = None
        else:
            run.step("Quick read (AI refinement continues in the background)", 2, 2)
            extracted = ProfileAgent().quick_extract(text)
            job_id = cv_refine.start(user_id, text, filename) if text.strip() else None
        run.set_output({"extraction_method": extracted.get("extraction_method"), "facts": len(extracted.get("facts", [])),
                        "missing_fields": extracted.get("missing_fields", []), "refining": job_id is not None})
        return _extraction_body(filename, text, extracted, job_id)


@router.get("/refine/{job_id}")
def get_refinement(job_id: str, user_id: int = Depends(get_current_user_id)):
    """Status of the background AI refinement: running | done | failed (+ the refined extraction when done)."""
    job = cv_refine.get(job_id, user_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Refinement job not found (it may have expired)")
    body: Dict[str, Any] = {"status": job["status"], "error": job.get("error")}
    if job.get("result"):
        r = job["result"]
        body.update({k: r.get(k) for k in ("facts", "profile_data", "missing_fields", "followup_questions",
                                           "extraction_method", "dropped", "message", "needs_review", "conflicts")})
    return body


@router.post("/sync-profile")
async def sync_parsed_profile(data: SyncProfileRequest, user_id: int = Depends(get_current_user_id),
                              db: Session = Depends(get_db)):
    """Save the facts the user reviewed and confirmed on the confirm page (verified=True)."""
    facts = data.facts or []
    profile_data = filter_confirmed_profile_data(data.profile_data or {}, facts)
    profile = get_or_create_profile(db, user_id)

    for section in ("personal", "professional"):
        if profile_data.get(section):
            current = dict(getattr(profile, section) or {})
            current.update({k: v for k, v in profile_data[section].items() if v not in (None, "", [])})
            setattr(profile, section, current)
    if profile_data.get("skills"):
        profile.skills = normalize_skills(profile_data["skills"])
        prof = dict(profile.professional or {})
        prof["skills"] = flatten_skills(profile.skills)
        profile.professional = prof
    for section in ("experience", "education", "projects", "certifications"):
        if profile_data.get(section):
            setattr(profile, section, profile_data[section])
    recompute_completeness(profile)

    for f in facts:
        path = f.get("path") or f.get("field") or "document.fact"
        val = f.get("value", "")
        val_str = json.dumps(val) if isinstance(val, (list, dict)) else str(val)
        rows = db.query(ProfileFact).filter(ProfileFact.profile_id == profile.id, ProfileFact.path == path).all()
        if rows:
            rows[0].value, rows[0].verified = val_str, True
            for extra in rows[1:]:  # conflict resolved by this confirmation
                db.delete(extra)
        else:
            db.add(ProfileFact(profile_id=profile.id, path=path, value=val_str,
                               source=f.get("source", "document_upload"), verified=True))
    db.commit()
    db.refresh(profile)
    return {"status": "success", "completeness_pct": profile.completeness_pct, "profile": _profile_payload(profile)}


@router.post("/upload")
async def upload_document(file: UploadFile = File(...), wait: bool = Query(False), user_id: int = Depends(get_current_user_id),
                          db: Session = Depends(get_db)):
    """Upload a CV: the quick read is saved in seconds (facts need review); the AI refinement then
    improves the saved profile in the background (poll GET /documents/refine/{refine_job_id})."""
    filename = file.filename or "cv.pdf"
    with track_run(user_id, "cv", f"Extract career profile from {filename}",
                   input_summary={"filename": filename, "content_type": file.content_type, "wait": wait}) as run:
        run.step("Read document", 1, 3)
        content = await _read_upload(file)
        text = await run_in_threadpool(_read_text_tracked, content, filename)
        run.step("AI extraction and grounding check" if wait else "Quick read", 2, 3)
        if wait:
            extracted = await run_in_threadpool(ProfileAgent().extract_from_text, text)
        else:
            extracted = ProfileAgent().quick_extract(text)
        run.step("Save profile (facts need your review)", 3, 3)
        result = save_extraction(db, user_id, extracted, source="document_upload")
        db.commit()
        profile = result["profile"]
        db.refresh(profile)
        job_id = cv_refine.start(user_id, text, filename, save_source="document_upload") if (not wait and text.strip()) else None
        if result["conflicts"]:
            run.warn(f"{len(result['conflicts'])} value(s) differ from facts you already confirmed; kept yours: "
                     + ", ".join(result["conflicts"][:5]))
        run.set_output({"extraction_method": extracted.get("extraction_method"), "facts": len(result["facts"]),
                        "needs_review": result["needs_review"], "conflicts": result["conflicts"],
                        "completeness_pct": profile.completeness_pct, "refining": job_id is not None})
        return {
            "status": "success",
            "filename": filename,
            "completeness_pct": profile.completeness_pct,
            "facts": result["facts"],
            "needs_review": result["needs_review"],
            "conflicts": result["conflicts"],
            "extraction_method": extracted.get("extraction_method"),
            "dropped": extracted.get("dropped", []),
            "missing_fields": extracted.get("missing_fields", []),
            "message": extracted.get("message", ""),
            "profile": _profile_payload(profile),
            "refine_job_id": job_id,
            "refining": job_id is not None,
        }

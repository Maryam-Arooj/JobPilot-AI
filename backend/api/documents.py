import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..ai_agents.profile_agent import flatten_skills, normalize_skills
from ..db.database import get_db
from ..models.career_profile import CareerProfile, ProfileFact
from ..services.agent_runs import track_run
from ..services.auth_middleware import get_current_user_id
from ..services.document_service import extract_text_and_profile
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


@router.post("/parse")
async def parse_document(file: UploadFile = File(...), user_id: int = Depends(get_current_user_id)):
    """Read a CV and return the grounded extraction for review. Nothing is saved."""
    filename = file.filename or "cv.pdf"
    with track_run(user_id, "cv", f"Read CV for review: {filename}",
                   input_summary={"filename": filename, "content_type": file.content_type}) as run:
        run.step("Read document", 1, 2)
        content = await _read_upload(file)
        run.step("AI extraction and grounding check", 2, 2)
        text, extracted = await run_in_threadpool(extract_text_and_profile, content, filename)
        run.set_output({"extraction_method": extracted.get("extraction_method"), "facts": len(extracted.get("facts", [])),
                        "dropped_values": len(extracted.get("dropped", [])), "missing_fields": extracted.get("missing_fields", [])})
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
        }


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
async def upload_document(file: UploadFile = File(...), user_id: int = Depends(get_current_user_id),
                          db: Session = Depends(get_db)):
    """Upload a CV: extract a grounded profile and save it. Facts are saved for review (unverified)."""
    filename = file.filename or "cv.pdf"
    with track_run(user_id, "cv", f"Extract career profile from {filename}",
                   input_summary={"filename": filename, "content_type": file.content_type}) as run:
        run.step("Read document", 1, 3)
        content = await _read_upload(file)
        run.step("AI extraction and grounding check", 2, 3)
        _, extracted = await run_in_threadpool(extract_text_and_profile, content, filename)
        run.step("Save profile (facts need your review)", 3, 3)
        result = save_extraction(db, user_id, extracted, source="document_upload")
        db.commit()
        profile = result["profile"]
        db.refresh(profile)
        if result["conflicts"]:
            run.warn(f"{len(result['conflicts'])} value(s) differ from facts you already confirmed; kept yours: "
                     + ", ".join(result["conflicts"][:5]))
        run.set_output({"extraction_method": extracted.get("extraction_method"), "facts": len(result["facts"]),
                        "needs_review": result["needs_review"], "conflicts": result["conflicts"],
                        "completeness_pct": profile.completeness_pct})
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
        }

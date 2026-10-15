import json
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db.database import get_db
from ..models.career_profile import CareerProfile, ProfileFact
from ..services.auth_middleware import get_current_user_id
from ..services.profile_crud import get_profile_by_user
from ..services.profile_service import calculate_completeness
from ..services.document_service import extract_facts_from_bytes, extract_text_from_file_bytes

from pydantic import BaseModel
from typing import Optional, List, Any, Dict

router = APIRouter(prefix="/documents", tags=["documents"])

class SyncProfileRequest(BaseModel):
    profile_data: Optional[Dict[str, Any]] = None
    facts: Optional[List[Dict[str, Any]]] = None

@router.post("/parse")
async def parse_document(file: UploadFile = File(...), user_id: int = Depends(get_current_user_id)):
    content = await file.read()
    filename = file.filename or "cv.pdf"
    text = extract_text_from_file_bytes(content, filename)
    extracted = extract_facts_from_bytes(content, filename)
    facts = extracted.get("facts", [])
    profile_data = extracted.get("profile_data", {})
    return {
        "filename": filename,
        "facts": facts,
        "profile_data": profile_data,
        "text": text,
        "missing_fields": extracted.get("missing_fields", []),
        "followup_questions": extracted.get("followup_questions", [])
    }

@router.post("/sync-profile")
async def sync_parsed_profile(
    data: SyncProfileRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Commit confirmed/edited facts and structured profile directly to user's CareerProfile in PostgreSQL.
    """
    profile_data = data.profile_data or {}
    facts = data.facts or []

    profile = get_profile_by_user(db, user_id)
    if not profile:
        profile = CareerProfile(user_id=user_id)
        db.add(profile)
        db.flush()

    if profile_data.get("personal"):
        current_personal = dict(profile.personal or {})
        for k, v in profile_data["personal"].items():
            if v:
                current_personal[k] = v
        profile.personal = current_personal

    if profile_data.get("professional"):
        current_prof = dict(profile.professional or {})
        for k, v in profile_data["professional"].items():
            if v:
                current_prof[k] = v
        profile.professional = current_prof

    if profile_data.get("skills"):
        profile.skills = profile_data["skills"]

    if profile_data.get("experience"):
        profile.experience = profile_data["experience"]

    if profile_data.get("education"):
        profile.education = profile_data["education"]

    if profile_data.get("projects"):
        profile.projects = profile_data["projects"]

    if profile_data.get("certifications"):
        profile.certifications = profile_data["certifications"]

    combined = {
        "personal": profile.personal,
        "professional": profile.professional,
        "education": profile.education,
        "experience": profile.experience,
        "skills": profile.skills,
        "projects": profile.projects,
        "certifications": profile.certifications,
    }
    profile.completeness_pct = calculate_completeness(combined)

    for f in facts:
        path = f.get("path") or f.get("field") or "document.fact"
        val = f.get("value", "")
        val_str = json.dumps(val) if isinstance(val, (list, dict)) else str(val)
        existing_fact = db.query(ProfileFact).filter(
            ProfileFact.profile_id == profile.id,
            ProfileFact.path == path
        ).first()
        if not existing_fact:
            db.add(ProfileFact(
                profile_id=profile.id,
                path=path,
                value=val_str,
                source=f.get("source", "document_upload"),
                verified=True
            ))
        else:
            existing_fact.value = val_str
            existing_fact.verified = True

    db.commit()
    db.refresh(profile)

    return {
        "status": "success",
        "completeness_pct": profile.completeness_pct,
        "profile": {
            "personal": profile.personal,
            "professional": profile.professional,
            "skills": profile.skills,
            "experience": profile.experience,
            "education": profile.education,
            "certifications": profile.certifications,
            "projects": profile.projects
        }
    }

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Directly upload CV document (.pdf, .docx, .txt), extract structured career profile
    using NVIDIA LLM and update user's profile and verified facts in database.
    """
    content = await file.read()
    filename = file.filename or "cv.pdf"

    extracted = extract_facts_from_bytes(content, filename)
    facts_raw = extracted.get("facts", [])
    profile_data = extracted.get("profile_data", {})

    profile = get_profile_by_user(db, user_id)
    if not profile:
        profile = CareerProfile(user_id=user_id)
        db.add(profile)
        db.flush()

    if profile_data.get("personal"):
        current_personal = profile.personal or {}
        for k, v in profile_data["personal"].items():
            if v:
                current_personal[k] = v
        profile.personal = current_personal

    if profile_data.get("professional"):
        current_prof = profile.professional or {}
        for k, v in profile_data["professional"].items():
            if v:
                current_prof[k] = v
        profile.professional = current_prof

    if profile_data.get("skills"):
        profile.skills = profile_data["skills"]

    if profile_data.get("experience"):
        profile.experience = profile_data["experience"]

    if profile_data.get("education"):
        profile.education = profile_data["education"]

    if profile_data.get("projects"):
        profile.projects = profile_data["projects"]

    if profile_data.get("certifications"):
        profile.certifications = profile_data["certifications"]

    combined = {
        "personal": profile.personal,
        "professional": profile.professional,
        "education": profile.education,
        "experience": profile.experience,
        "skills": profile.skills,
        "projects": profile.projects,
        "certifications": profile.certifications,
    }
    profile.completeness_pct = calculate_completeness(combined)

    for f in facts_raw:
        val_str = json.dumps(f["value"]) if isinstance(f["value"], (list, dict)) else str(f["value"])
        existing_fact = db.query(ProfileFact).filter(
            ProfileFact.profile_id == profile.id,
            ProfileFact.path == f["path"]
        ).first()
        if not existing_fact:
            db.add(ProfileFact(
                profile_id=profile.id,
                path=f["path"],
                value=val_str,
                source="document_upload",
                verified=True
            ))
        else:
            existing_fact.value = val_str
            existing_fact.verified = True

    db.commit()
    db.refresh(profile)

    return {
        "status": "success",
        "filename": filename,
        "completeness_pct": profile.completeness_pct,
        "facts": facts_raw,
        "profile": {
            "personal": profile.personal,
            "professional": profile.professional,
            "skills": profile.skills,
            "experience": profile.experience,
            "education": profile.education
        }
    }

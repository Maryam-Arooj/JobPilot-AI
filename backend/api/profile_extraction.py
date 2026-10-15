import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..db.database import get_db
from ..models.career_profile import CareerProfile, ProfileFact
from ..services.auth_middleware import get_current_user_id
from ..services.profile_crud import get_profile_by_user
from ..services.profile_service import calculate_completeness
from ..services.document_service import extract_facts_from_bytes
from ..ai_agents.profile_agent import ProfileAgent

router = APIRouter(prefix="/profiles/me/extract", tags=["profile_extraction"])
agent = ProfileAgent()

class ExtractIn(BaseModel):
    text: str
    auto_save: bool = True

@router.post("")
def extract_profile(
    data: ExtractIn,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Extract structured facts and profile sections from CV / bio text using NVIDIA LLM.
    Automatically saves to the user's database CareerProfile if auto_save is True.
    """
    extracted = agent.extract_from_text(data.text)
    facts_raw = extracted.get("facts", [])
    profile_data = extracted.get("profile_data", {})
    missing = extracted.get("missing_fields", [])
    followups = extracted.get("followup_questions", [])

    if data.auto_save and profile_data:
        profile = get_profile_by_user(db, user_id)
        if not profile:
            profile = CareerProfile(user_id=user_id)
            db.add(profile)
            db.flush()

        # Merge extracted fields safely into profile
        if profile_data.get("personal"):
            current_personal = profile.personal or {}
            for k, v in profile_data["personal"].items():
                if v and not current_personal.get(k):
                    current_personal[k] = v
                elif v and (not current_personal.get(k) or len(str(current_personal.get(k))) < len(str(v))):
                    current_personal[k] = v
            profile.personal = current_personal

        if profile_data.get("professional"):
            current_prof = profile.professional or {}
            for k, v in profile_data["professional"].items():
                if v and not current_prof.get(k):
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

        # Recalculate completeness
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

        # Save/upsert facts
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
                    source=f.get("source", "nvidia_llm"),
                    verified=True
                ))
            else:
                existing_fact.value = val_str
                existing_fact.verified = True

        db.commit()
        db.refresh(profile)

    return {
        "status": "success",
        "facts": facts_raw,
        "profile_data": profile_data,
        "missing_fields": missing,
        "followup_questions": followups,
        "saved_to_profile": data.auto_save
    }

@router.post("/upload")
async def upload_cv_document(
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Directly upload CV file (.pdf, .docx, .txt), extract structured profile with AI, and save to DB.
    """
    file_bytes = await file.read()
    filename = file.filename or "cv.pdf"
    
    extracted = extract_facts_from_bytes(file_bytes, filename)
    facts_raw = extracted.get("facts", [])
    profile_data = extracted.get("profile_data", {})
    missing = extracted.get("missing_fields", [])
    followups = extracted.get("followup_questions", [])

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
                source="cv_upload",
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
        "facts_count": len(facts_raw),
        "facts": facts_raw,
        "profile_data": profile_data,
        "missing_fields": missing,
        "followup_questions": followups
    }

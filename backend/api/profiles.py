from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db.database import get_db
from ..models.career_profile import CareerProfile, User
from ..schemas.profile import CareerProfileCreate
from ..services.profile_service import calculate_completeness
from ..services.profile_crud import get_profile_by_user, upsert_profile
from ..services.auth_middleware import get_current_user_id

router = APIRouter(prefix="/profiles", tags=["profiles"])

def _serialize_profile(profile: CareerProfile, db: Session = None) -> dict:
    facts = []
    if hasattr(profile, 'facts') and profile.facts:
        for f in profile.facts:
            facts.append({
                "id": f.id,
                "fact_key": f.path,
                "fact_value": f.value,
                "source": f.source,
                "verified": f.verified,
            })
    
    personal = dict(profile.personal or {})
    if db and profile.user_id:
        user = db.query(User).filter(User.id == profile.user_id).first()
        if user and not personal.get("email"):
            personal["email"] = user.email
        if user and not personal.get("name"):
            personal["name"] = user.email.split("@")[0].replace(".", " ").capitalize()

    return {
        "id": profile.id,
        "user_id": profile.user_id,
        "completeness_pct": profile.completeness_pct or 0,
        "personal": personal,
        "professional": profile.professional or {},
        "education": profile.education or [],
        "experience": profile.experience or [],
        "skills": profile.skills or {},
        "projects": profile.projects or [],
        "certifications": profile.certifications or [],
        "achievements": profile.achievements or [],
        "publications": profile.publications or [],
        "portfolio": profile.portfolio or [],
        "preferences": profile.preferences or {},
        "facts": facts,
        "updated_at": str(profile.updated_at) if profile.updated_at else None,
    }

@router.get("/me")
def get_my_profile(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    profile = get_profile_by_user(db, user_id)
    if not profile:
        # Auto-create empty profile for first-time users — never invent data
        profile = CareerProfile(
            user_id=user_id,
            personal={},
            professional={},
            education=[],
            experience=[],
            skills={},
            projects=[],
            certifications=[],
            achievements=[],
            publications=[],
            portfolio=[],
            preferences={},
            completeness_pct=0,
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return _serialize_profile(profile, db)

@router.put("/me")
def update_my_profile(
    data: CareerProfileCreate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    profile = get_profile_by_user(db, user_id)
    if not profile:
        profile = CareerProfile(user_id=user_id)
        db.add(profile)

    # Merge, don't replace: keys the form does not send (e.g. headline, linkedin) are kept.
    # A key sent as "" or null clears that field.
    def _merge(current, incoming):
        merged = dict(current or {})
        for k, v in (incoming or {}).items():
            if v is None or v == "" or v == []:
                merged.pop(k, None)
            else:
                merged[k] = v
        return merged

    if data.personal is not None:
        profile.personal = _merge(profile.personal, data.personal)
    if data.professional is not None:
        profile.professional = _merge(profile.professional, data.professional)
        if isinstance(data.professional.get("skills"), list):
            # the edited list becomes the single source of skills (no duplicate categories)
            from ..ai_agents.profile_agent import normalize_skills, flatten_skills
            profile.skills = normalize_skills({"technical": data.professional["skills"]})
            prof = dict(profile.professional); prof["skills"] = flatten_skills(profile.skills)
            profile.professional = prof
    if hasattr(data, 'education') and data.education is not None:
        profile.education = data.education
    if hasattr(data, 'experience') and data.experience is not None:
        profile.experience = data.experience
    if hasattr(data, 'skills') and data.skills is not None:
        from ..ai_agents.profile_agent import normalize_skills
        profile.skills = normalize_skills(data.skills)
    if hasattr(data, 'projects') and data.projects is not None:
        profile.projects = data.projects
    if hasattr(data, 'certifications') and data.certifications is not None:
        profile.certifications = data.certifications
    if hasattr(data, 'achievements') and data.achievements is not None:
        profile.achievements = data.achievements

    combined = {
        "personal": profile.personal,
        "professional": profile.professional,
        "education": profile.education,
        "experience": profile.experience,
        "skills": profile.skills,
        "projects": profile.projects,
        "certifications": profile.certifications,
        "achievements": profile.achievements,
    }
    profile.completeness_pct = calculate_completeness(combined)
    db.commit()
    db.refresh(profile)
    return _serialize_profile(profile, db)

@router.get("/")
def list_profiles(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    profiles = db.query(CareerProfile).filter(CareerProfile.user_id == user_id).all()
    return [_serialize_profile(p, db) for p in profiles]

@router.get("/{profile_id}")
def get_profile(profile_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    profile = db.query(CareerProfile).filter(
        CareerProfile.id == profile_id,
        CareerProfile.user_id == user_id
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Not found")
    return _serialize_profile(profile, db)

@router.post("/")
def create_profile(data: CareerProfileCreate, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    existing = get_profile_by_user(db, user_id)
    if existing:
        return _serialize_profile(existing, db)
    profile = CareerProfile(
        user_id=user_id,
        personal=data.personal,
        professional=data.professional,
        completeness_pct=calculate_completeness({
            "personal": data.personal,
            "professional": data.professional
        })
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return _serialize_profile(profile)

@router.patch("/{profile_id}/confirm-facts")
def confirm_facts(profile_id: int, approvals: dict, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    profile = db.query(CareerProfile).filter(
        CareerProfile.id == profile_id,
        CareerProfile.user_id == user_id
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Not found")
    return {"status": "confirmed", "approvals": approvals}

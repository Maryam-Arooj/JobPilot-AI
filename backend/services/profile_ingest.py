"""Save CV-extraction results into a user's CareerProfile.

Rules (CV Agent):
- Extracted facts are saved UNVERIFIED. Only the user's confirmation (confirm page /
  /profiles/me/facts/confirm or /documents/sync-profile) marks facts verified.
- A value the user already confirmed is never overwritten by an extraction: the new value is
  stored as a separate unverified fact (a conflict the user can resolve).
- Lists (experience, education, projects, certifications, skills) are replaced only by an AI
  extraction; the literal fallback only fills sections that are still empty.
"""
import json
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from ..ai_agents.profile_agent import flatten_skills, normalize_skills
from ..models.career_profile import CareerProfile, ProfileFact
from .profile_service import calculate_completeness

LIST_SECTIONS = ("experience", "education", "projects", "certifications")


def _val_str(v: Any) -> str:
    return json.dumps(v) if isinstance(v, (list, dict)) else str(v)


def get_or_create_profile(db: Session, user_id: int) -> CareerProfile:
    profile = db.query(CareerProfile).filter(CareerProfile.user_id == user_id).first()
    if not profile:
        profile = CareerProfile(user_id=user_id)
        db.add(profile)
        db.flush()
    return profile


def _verified_values(db: Session, profile_id: int) -> Dict[str, str]:
    return {f.path: f.value for f in db.query(ProfileFact)
            .filter(ProfileFact.profile_id == profile_id, ProfileFact.verified == True).all()}  # noqa: E712


def recompute_completeness(profile: CareerProfile) -> int:
    profile.completeness_pct = calculate_completeness({
        "personal": profile.personal, "professional": profile.professional, "education": profile.education,
        "experience": profile.experience, "skills": profile.skills if isinstance(profile.skills, dict) else {},
        "projects": profile.projects, "certifications": profile.certifications,
    })
    return profile.completeness_pct


def save_extraction(db: Session, user_id: int, extracted: Dict[str, Any], source: str) -> Dict[str, Any]:
    """Merge an extraction into the profile and store its facts unverified. Caller commits."""
    profile = get_or_create_profile(db, user_id)
    data = extracted.get("profile_data") or {}
    is_ai = extracted.get("extraction_method") == "llm"
    verified = _verified_values(db, profile.id)
    conflicts: List[str] = []

    for section in ("personal", "professional"):
        current = dict(getattr(profile, section) or {})
        for k, v in (data.get(section) or {}).items():
            if v in (None, "", [], {}):
                continue
            path = f"{section}.{k}"
            if path in verified and verified[path] != _val_str(v):
                conflicts.append(path)  # keep the confirmed value
                continue
            if current.get(k) and not is_ai and k not in ("skills",):
                continue  # literal fallback never replaces existing data
            current[k] = v
        setattr(profile, section, current)

    new_skills = normalize_skills(data.get("skills") or {})
    if flatten_skills(new_skills) and (is_ai or not flatten_skills(profile.skills or {})):
        profile.skills = new_skills
        prof = dict(profile.professional or {})
        prof["skills"] = flatten_skills(new_skills)
        profile.professional = prof
    elif isinstance(profile.skills, (dict, list)):
        profile.skills = normalize_skills(profile.skills)  # also removes old duplicates

    for section in LIST_SECTIONS:
        items = data.get(section) or []
        if items and (is_ai or not getattr(profile, section)):
            setattr(profile, section, items)
            if section != "certifications":
                # facts for the old list entries no longer apply
                db.query(ProfileFact).filter(ProfileFact.profile_id == profile.id,
                                             ProfileFact.verified == False,  # noqa: E712
                                             ProfileFact.path.like(f"{section}[%")).delete(synchronize_session=False)

    recompute_completeness(profile)

    saved_facts = []
    for f in extracted.get("facts") or []:
        path, val = f["path"], _val_str(f["value"])
        existing = (db.query(ProfileFact)
                    .filter(ProfileFact.profile_id == profile.id, ProfileFact.path == path)
                    .order_by(ProfileFact.verified.desc()).all())
        verified_row = next((r for r in existing if r.verified), None)
        pending_row = next((r for r in existing if not r.verified), None)
        if verified_row is not None and verified_row.value == val:
            row = verified_row  # already confirmed with this exact value
        elif pending_row is not None:
            pending_row.value, pending_row.source = val, source
            row = pending_row
        else:
            row = ProfileFact(profile_id=profile.id, path=path, value=val, source=source, verified=False)
            db.add(row)
        db.flush()
        if verified_row is not None and verified_row.value != val and path not in conflicts:
            conflicts.append(path)
        saved_facts.append({**f, "id": row.id, "verified": bool(row.verified)})

    return {
        "profile": profile,
        "facts": saved_facts,
        "needs_review": sum(1 for f in saved_facts if not f["verified"]),
        "conflicts": conflicts,
    }


def filter_confirmed_profile_data(profile_data: Dict[str, Any], facts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """On sync, keep only the parts of profile_data that the user kept as facts (rejected facts are gone)."""
    paths = {str(f.get("path") or f.get("field") or "") for f in facts}
    out: Dict[str, Any] = {}
    for section in ("personal", "professional"):
        src = profile_data.get(section) or {}
        kept = {k: v for k, v in src.items() if f"{section}.{k}" in paths}
        if section == "professional":
            for derived in ("experience_years", "skills", "target_role", "title"):
                if derived in src and (derived != "skills" or "skills" in paths):
                    kept[derived] = src[derived]
        if kept:
            out[section] = kept
    if "skills" in paths and profile_data.get("skills"):
        out["skills"] = profile_data["skills"]
    if "certifications" in paths and profile_data.get("certifications"):
        out["certifications"] = profile_data["certifications"]
    for section in ("experience", "education", "projects"):
        items = profile_data.get(section) or []
        kept = [it for i, it in enumerate(items) if f"{section}[{i}]" in paths]
        if kept:
            out[section] = kept
    return out

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from ..db.database import get_db
from ..models.career_profile import CareerProfile, ProfileFact
from ..models.audit import ProfileFactHistory
from ..services.auth_middleware import get_current_user_id

router = APIRouter(prefix="/profiles/me/facts", tags=["conflict"])

class ResolveIn(BaseModel):
    path: str
    keep_existing: bool
    fact_id: int

@router.post("/resolve-conflict")
def resolve_conflict(data: ResolveIn, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    profile = db.query(CareerProfile).filter(CareerProfile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    fact = db.query(ProfileFact).filter(ProfileFact.id == data.fact_id, ProfileFact.profile_id == profile.id).first()
    if not fact:
        raise HTTPException(status_code=404, detail="Fact not found")
    
    # Find existing confirmed fact for same path
    existing = db.query(ProfileFact).filter(
        ProfileFact.profile_id == profile.id,
        ProfileFact.path == data.path,
        ProfileFact.verified == True
    ).first()
    
    if existing and data.keep_existing:
        # Preserve existing, discard new
        db.delete(fact)
        db.commit()
        return {"path": data.path, "decision": "kept_existing", "value": existing.value}
    else:
        # Preserve provenance via history
        if existing:
            hist = ProfileFactHistory(
                fact_id=existing.id,
                old_value=existing.value,
                new_value=fact.value,
                change_reason="conflict_resolution",
                changed_by=str(user_id)
            )
            db.add(hist)
            existing.value = fact.value
        else:
            fact.verified = True
        db.commit()
        return {"path": data.path, "decision": "updated", "value": fact.value}

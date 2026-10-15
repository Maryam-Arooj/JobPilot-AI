from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db.database import get_db
from ..models.career_profile import CareerProfile, ProfileFact
from pydantic import BaseModel
from typing import List
from ..services.auth_middleware import get_current_user_id

router = APIRouter(prefix="/profiles/me/facts", tags=["facts"])

class FactConfirmIn(BaseModel):
    fact_ids: List[int]
    action: str  # confirm, reject, edit

@router.post("/confirm")
def confirm_facts(data: FactConfirmIn, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    # Verify facts belong to user's profile
    profile = db.query(CareerProfile).filter(CareerProfile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    facts = db.query(ProfileFact).filter(ProfileFact.id.in_(data.fact_ids), ProfileFact.profile_id == profile.id).all()
    for f in facts:
        f.verified = True
    db.commit()
    return {"confirmed": len(facts)}

@router.post("/reject")
def reject_facts(data: FactConfirmIn, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    profile = db.query(CareerProfile).filter(CareerProfile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    facts = db.query(ProfileFact).filter(ProfileFact.id.in_(data.fact_ids), ProfileFact.profile_id == profile.id).all()
    for f in facts:
        db.delete(f)
    db.commit()
    return {"rejected": len(facts)}

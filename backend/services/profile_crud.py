from sqlalchemy.orm import Session
from ..models.career_profile import CareerProfile, ProfileFact
from typing import List

def get_profile_by_user(db: Session, user_id: int) -> CareerProfile:
    return db.query(CareerProfile).filter(CareerProfile.user_id == user_id).first()

def upsert_profile(db: Session, user_id: int, data: dict) -> CareerProfile:
    profile = get_profile_by_user(db, user_id)
    if not profile:
        profile = CareerProfile(user_id=user_id)
        db.add(profile)
    for k, v in data.items():
        setattr(profile, k, v)
    db.commit()
    db.refresh(profile)
    return profile

def add_fact(db: Session, profile_id: int, path: str, value: str, source: str, verified: bool=False):
    fact = ProfileFact(profile_id=profile_id, path=path, value=value, source=source, verified=verified)
    db.add(fact)
    db.commit()
    return fact

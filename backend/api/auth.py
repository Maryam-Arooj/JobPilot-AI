from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
from ..db.database import get_db
from ..models.career_profile import User, CareerProfile
from ..services.auth_service import hash_password, verify_password, create_token
from ..services.auth_middleware import get_current_user_id

router = APIRouter(prefix="/auth", tags=["auth"])

class AuthIn(BaseModel):
    email: str
    password: str
    name: Optional[str] = None

@router.post("/login")
def login(data: AuthIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_token(user.id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user.id,
        "email": user.email
    }

@router.post("/register")
def register(data: AuthIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="An account with this email already exists.")
    user = User(email=data.email, password_hash=hash_password(data.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    # Initialize empty career profile for new user
    profile = CareerProfile(
        user_id=user.id,
        personal={"name": data.name or data.email.split("@")[0], "email": data.email},
        professional={},
        completeness_pct=10
    )
    db.add(profile)
    db.commit()

    token = create_token(user.id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user.id,
        "email": user.email,
        "status": "created"
    }

@router.get("/me")
def get_me(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    profile = db.query(CareerProfile).filter(CareerProfile.user_id == user_id).first()
    return {
        "id": user.id,
        "email": user.email,
        "name": profile.personal.get("name") if (profile and profile.personal) else user.email.split("@")[0],
        "created_at": str(user.created_at) if hasattr(user, 'created_at') else None
    }


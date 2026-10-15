from pydantic import BaseModel
from typing import Any, List, Optional

class Personal(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    country: Optional[str] = None

class CareerProfileCreate(BaseModel):
    personal: Optional[dict] = None
    professional: Optional[dict] = None
    education: Optional[List[dict]] = None
    experience: Optional[List[dict]] = None
    skills: Optional[dict] = None
    projects: Optional[List[dict]] = None
    certifications: Optional[List[Any]] = None
    achievements: Optional[List[dict]] = None
    publications: Optional[List[dict]] = None
    portfolio: Optional[List[dict]] = None
    preferences: Optional[dict] = None

class ProfileFactIn(BaseModel):
    path: str
    value: Any
    source: str
    verified: bool = False

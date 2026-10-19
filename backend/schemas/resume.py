from pydantic import BaseModel, Field, field_validator
from typing import Any, Dict, List, Optional

class ResumeSection(BaseModel):
    id: str
    title: str
    visible: bool = True
    order: int = 0
    content: Any

class ResumeDocumentSchema(BaseModel):
    header: Dict[str, Any]
    professional_summary: Optional[str] = None
    experience: List[Dict[str, Any]] = []
    education: List[Dict[str, Any]] = []
    skills: List[str] = []
    projects: List[Dict[str, Any]] = []
    certifications: List[Any] = []
    achievements: List[Dict[str, Any]] = []
    publications: List[Dict[str, Any]] = []
    links: List[Dict[str, Any]] = []
    sections_order: List[str] = []
    template: str
    target_role: Optional[str] = None
    source_profile_version: Optional[str] = None

class ResumeCreate(BaseModel):
    template: str
    target_role: Optional[str] = None
    title: str

class ResumeGenerate(BaseModel):
    target_role: Optional[str] = None
    template: Optional[str] = None
    # The Resume Studio editor's current CV. When given, it is saved as-is (the user's edits);
    # otherwise the resume is built from the career profile.
    custom_content: Optional[Dict[str, Any]] = None

class ResumeUpdate(BaseModel):
    content_snapshot: ResumeDocumentSchema

class TailorExperience(BaseModel):
    role: str = ""
    company: str = ""
    location: Optional[str] = ""
    period: str = ""
    bullets: List[str] = []

class TailorCV(BaseModel):
    title: str = ""
    summary: str = ""
    experience: List[TailorExperience] = []
    skills: List[str] = []
    education: List[Dict[str, Any]] = []
    certifications: List[Any] = []

class ResumeTailorRequest(BaseModel):
    target_role: str = Field(..., min_length=1, max_length=120)
    job_description: Optional[str] = Field(None, max_length=20000)
    job_id: Optional[int] = None
    cv: TailorCV

    @field_validator("target_role")
    @classmethod
    def _target_role_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("target_role is required")
        return v.strip()

class ResumeExportRequest(BaseModel):
    version_id: int
    format: str  # pdf or docx

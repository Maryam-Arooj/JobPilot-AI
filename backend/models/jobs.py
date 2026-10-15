from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..db.database import Base

class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    company = Column(String, nullable=False)
    location = Column(String)
    remote = Column(Boolean, default=False)
    employment_type = Column(String)
    salary = Column(String)
    description = Column(Text)
    requirements = Column(JSON, default=list)
    preferred_skills = Column(JSON, default=list)
    responsibilities = Column(JSON, default=list)
    application_url = Column(String)
    source = Column(String)
    source_url = Column(String)
    posted_at = Column(DateTime(timezone=True))
    retrieved_at = Column(DateTime(timezone=True), server_default=func.now())
    extraction_method = Column(String)
    technologies = Column(JSON, default=list)
    seniority = Column(String)
    experience_years = Column(Integer)
    industry = Column(String)
    job_type = Column(String)
    country = Column(String)
    city = Column(String)
    normalized_title = Column(String)
    normalized_company = Column(String)

    sources = relationship("JobSource", back_populates="job", cascade="all, delete-orphan")
    matches = relationship("JobMatch", back_populates="job", cascade="all, delete-orphan")

class JobSource(Base):
    __tablename__ = "job_sources"
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    provider = Column(String, nullable=False)
    provider_record_id = Column(String)
    source_url = Column(String)
    retrieved_at = Column(DateTime(timezone=True), server_default=func.now())
    raw_data = Column(JSON)

    job = relationship("Job", back_populates="sources")

class JobRequirement(Base):
    __tablename__ = "job_requirements"
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    type = Column(String)  # required / preferred
    text = Column(Text)
    skill = Column(String)

class JobMatch(Base):
    __tablename__ = "job_matches"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    overall_alignment = Column(String)
    skills_match = Column(JSON)
    experience_match = Column(JSON)
    education_match = Column(JSON)
    location_match = Column(JSON)
    responsibility_match = Column(JSON)
    matched_requirements = Column(JSON, default=list)
    gaps = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    job = relationship("Job", back_populates="matches")

class JobMatchEvidence(Base):
    __tablename__ = "job_match_evidence"
    id = Column(Integer, primary_key=True)
    match_id = Column(Integer, ForeignKey("job_matches.id"), nullable=False)
    evidence_type = Column(String)
    career_profile_fact_path = Column(String)
    job_requirement_text = Column(String)
    explanation = Column(Text)

class JobSearch(Base):
    __tablename__ = "job_searches"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    natural_language_query = Column(Text)
    structured_intent = Column(JSON)
    provider_status = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    results_count = Column(Integer, default=0)

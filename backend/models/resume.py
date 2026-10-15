from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..db.database import Base

class ResumeDocument(Base):
    __tablename__ = "resume_documents"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    career_profile_id = Column(Integer, ForeignKey("career_profiles.id"), nullable=False)
    template = Column(String, nullable=False)
    target_role = Column(String, nullable=True)
    title = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    approved = Column(Boolean, default=False)

    user = relationship("User")
    career_profile = relationship("CareerProfile")
    versions = relationship("ResumeVersion", back_populates="document", cascade="all, delete-orphan")

class ResumeVersion(Base):
    __tablename__ = "resume_versions"
    id = Column(Integer, primary_key=True)
    resume_id = Column(Integer, ForeignKey("resume_documents.id"), nullable=False)
    version_number = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    target_role = Column(String, nullable=True)
    content_snapshot = Column(JSON, nullable=False)
    source_profile_version = Column(String, nullable=True)
    status = Column(String, default="draft")

    document = relationship("ResumeDocument", back_populates="versions")
    quality_reports = relationship("ResumeQualityReport", back_populates="version", cascade="all, delete-orphan")

class ResumeQualityReport(Base):
    __tablename__ = "resume_quality_reports"
    id = Column(Integer, primary_key=True)
    version_id = Column(Integer, ForeignKey("resume_versions.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(String, nullable=False)
    issues = Column(JSON, default=list)
    warnings = Column(JSON, default=list)
    suggestions = Column(JSON, default=list)

    version = relationship("ResumeVersion", back_populates="quality_reports")

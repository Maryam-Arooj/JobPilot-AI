from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..db.database import Base

class Application(Base):
    __tablename__ = "applications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    resume_version_id = Column(Integer, ForeignKey("resume_versions.id"), nullable=True)
    status = Column(String, default="PREPARING")  # PREPARING, DRAFT_READY, READY_FOR_REVIEW
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    job = relationship("Job")
    company = relationship("Company", back_populates="applications")
    resume_version = relationship("ResumeVersion")
    events = relationship("ApplicationEvent", back_populates="application", cascade="all, delete-orphan")
    email_versions = relationship("ApplicationEmailVersion", back_populates="application", cascade="all, delete-orphan")
    email_drafts = relationship("EmailDraft", back_populates="application", cascade="all, delete-orphan")

class ApplicationEvent(Base):
    __tablename__ = "application_events"
    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False)
    event_type = Column(String, nullable=False)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    application = relationship("Application", back_populates="events")

class ApplicationEmailVersion(Base):
    __tablename__ = "application_email_versions"
    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False)
    tone = Column(String, nullable=False)  # Formal, Technical, Concise, Networking, Cold Outreach
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    greeting = Column(String)
    closing = Column(String)
    referenced_profile_facts = Column(JSON, default=list)
    referenced_job_requirements = Column(JSON, default=list)
    referenced_company_claims = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    application = relationship("Application", back_populates="email_versions")

class EmailDraft(Base):
    __tablename__ = "email_drafts"
    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False)
    provider = Column(String, default="gmail")
    draft_id = Column(String, nullable=False)
    recipient = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    has_attachment = Column(Boolean, default=False)
    attachment_name = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    application = relationship("Application", back_populates="email_drafts")

class GmailConnection(Base):
    __tablename__ = "gmail_connections"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    email = Column(String, nullable=False)
    is_connected = Column(Boolean, default=True)
    access_token = Column(Text)
    refresh_token = Column(Text)
    token_expiry = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class CareerMemory(Base):
    __tablename__ = "career_memory"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    memory_type = Column(String)
    content = Column(Text)
    tags = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class JobAlert(Base):
    __tablename__ = "job_alerts"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    query = Column(String)
    filters = Column(JSON)
    frequency = Column(String, default="daily")
    active = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

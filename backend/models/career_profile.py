from sqlalchemy import Column, Integer, String, JSON, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..db.database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class CareerProfile(Base):
    __tablename__ = "career_profiles"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    personal = Column(JSON)
    professional = Column(JSON)
    education = Column(JSON)
    experience = Column(JSON)
    skills = Column(JSON)
    projects = Column(JSON)
    certifications = Column(JSON)
    achievements = Column(JSON)
    publications = Column(JSON)
    portfolio = Column(JSON)
    preferences = Column(JSON)
    completeness_pct = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    facts = relationship("ProfileFact", back_populates="profile", cascade="all, delete-orphan")

class ProfileFact(Base):
    __tablename__ = "profile_facts"
    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("career_profiles.id"), nullable=False)
    path = Column(String, nullable=False)  # e.g. "personal.name"
    value = Column(Text)
    source = Column(String, nullable=False)  # user, document, agent
    verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    profile = relationship("CareerProfile", back_populates="facts")

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..db.database import Base

class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True, index=True)
    official_website = Column(String)
    industry = Column(String)
    headquarters = Column(String)
    logo_url = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    research = relationship("CompanyResearch", back_populates="company", cascade="all, delete-orphan")
    applications = relationship("Application", back_populates="company")

class CompanyResearch(Base):
    __tablename__ = "company_research"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    overview = Column(Text)
    products_services = Column(JSON, default=list)
    technology_info = Column(JSON, default=list)
    engineering_info = Column(Text)
    mission_info = Column(Text)
    recent_news = Column(JSON, default=list)
    careers_url = Column(String)
    confidence_status = Column(String, default="verified")
    research_timestamp = Column(DateTime(timezone=True), server_default=func.now())

    company = relationship("Company", back_populates="research")
    sources = relationship("CompanyResearchSource", back_populates="research", cascade="all, delete-orphan")
    claims = relationship("CompanyResearchClaim", back_populates="research", cascade="all, delete-orphan")

class CompanyResearchSource(Base):
    __tablename__ = "company_research_sources"
    id = Column(Integer, primary_key=True, index=True)
    research_id = Column(Integer, ForeignKey("company_research.id"), nullable=False)
    source_url = Column(String, nullable=False)
    provider = Column(String, default="firecrawl/serp")
    retrieved_at = Column(DateTime(timezone=True), server_default=func.now())
    raw_data = Column(JSON)

    research = relationship("CompanyResearch", back_populates="sources")

class CompanyResearchClaim(Base):
    __tablename__ = "company_research_claims"
    id = Column(Integer, primary_key=True, index=True)
    research_id = Column(Integer, ForeignKey("company_research.id"), nullable=False)
    claim_text = Column(Text, nullable=False)
    source_url = Column(String)
    fact_type = Column(String, default="tech_stack")
    verified = Column(Boolean, default=True)

    research = relationship("CompanyResearch", back_populates="claims")

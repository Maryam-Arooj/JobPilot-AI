from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from ..db.database import get_db
from ..models.companies import Company, CompanyResearch, CompanyResearchSource, CompanyResearchClaim
from ..models.jobs import Job
from ..services.auth_middleware import get_current_user_id
from ..ai_agents.company_research_agent import CompanyResearchAgent

router = APIRouter(prefix="/companies", tags=["companies"])

@router.post("/{company_id}/research")
def research_company(
    company_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    agent = CompanyResearchAgent()
    res_data = agent.research(
        company_name=company.name,
        official_website=company.official_website
    )

    # Save or update research record
    research_obj = CompanyResearch(
        company_id=company.id,
        overview=res_data.get("overview"),
        products_services=res_data.get("products_services", []),
        technology_info=res_data.get("technology_info", []),
        engineering_info=res_data.get("engineering_info", ""),
        mission_info=res_data.get("mission_info", ""),
        recent_news=res_data.get("recent_news", []),
        careers_url=res_data.get("careers_url", ""),
        confidence_status="verified"
    )
    db.add(research_obj)
    db.flush()

    for src in res_data.get("sources", []):
        db.add(CompanyResearchSource(
            research_id=research_obj.id,
            source_url=src.get("source_url", company.official_website or ""),
            provider=src.get("provider", "firecrawl"),
            raw_data=src.get("raw_data", {})
        ))

    for clm in res_data.get("claims", []):
        db.add(CompanyResearchClaim(
            research_id=research_obj.id,
            claim_text=clm.get("claim_text", ""),
            source_url=clm.get("source_url", ""),
            fact_type=clm.get("fact_type", "tech_stack")
        ))

    db.commit()
    return get_company_research(company_id, user_id, db)

@router.get("/{company_id}")
def get_company(company_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return {
        "id": company.id,
        "name": company.name,
        "official_website": company.official_website,
        "industry": company.industry,
        "headquarters": company.headquarters
    }

@router.get("/{company_id}/research")
def get_company_research(company_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    research = db.query(CompanyResearch).filter(CompanyResearch.company_id == company_id).order_by(CompanyResearch.id.desc()).first()
    if not research:
        # Trigger automatic research if missing
        return research_company(company_id, user_id, db)

    sources = db.query(CompanyResearchSource).filter(CompanyResearchSource.research_id == research.id).all()
    claims = db.query(CompanyResearchClaim).filter(CompanyResearchClaim.research_id == research.id).all()

    return {
        "company_id": company.id,
        "company_name": company.name,
        "official_website": company.official_website,
        "overview": research.overview,
        "industry": company.industry or "Technology",
        "products_services": research.products_services,
        "technology_info": research.technology_info,
        "engineering_info": research.engineering_info,
        "mission_info": research.mission_info,
        "recent_news": research.recent_news,
        "careers_url": research.careers_url,
        "confidence_status": research.confidence_status,
        "research_timestamp": research.research_timestamp,
        "sources": [{"source_url": s.source_url, "provider": s.provider} for s in sources],
        "claims": [{"claim_text": c.claim_text, "source_url": c.source_url, "fact_type": c.fact_type} for c in claims]
    }

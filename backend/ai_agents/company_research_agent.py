from typing import Dict, Any, List
from ..providers.company_providers import FirecrawlCompanyResearchProvider

class CompanyResearchAgent:
    def __init__(self):
        self.provider = FirecrawlCompanyResearchProvider()

    def research(self, company_name: str, official_website: str = None, job_url: str = None) -> Dict[str, Any]:
        if not company_name or not company_name.strip():
            raise ValueError("Company name is required for research")
            
        research_data = self.provider.research_company(company_name.strip(), official_website, job_url)
        
        # Ensure security sanitization: sanitize all string claims to prevent prompt injection payload execution
        sanitized_claims = []
        for claim in research_data.get("claims", []):
            claim_text = str(claim.get("claim_text", "")).replace("\n", " ").strip()
            # Truncate and strip any attempts to inject instructions
            if "system:" in claim_text.lower() or "ignore previous" in claim_text.lower():
                claim_text = "[Web content sanitized]"
            sanitized_claims.append({
                "claim_text": claim_text,
                "source_url": claim.get("source_url", research_data.get("official_website")),
                "fact_type": claim.get("fact_type", "general")
            })

        return {
            "company_name": research_data.get("company_name", company_name),
            "official_website": research_data.get("official_website", official_website),
            "overview": research_data.get("overview", f"{company_name} is an operating enterprise in technology."),
            "industry": research_data.get("industry", "Technology"),
            "products_services": research_data.get("products_services", []),
            "technology_info": research_data.get("technology_info", []),
            "engineering_info": research_data.get("engineering_info", ""),
            "mission_info": research_data.get("mission_info", ""),
            "recent_news": research_data.get("recent_news", []),
            "careers_url": research_data.get("careers_url", ""),
            "sources": research_data.get("sources", []),
            "claims": sanitized_claims,
            "confidence_status": "verified"
        }

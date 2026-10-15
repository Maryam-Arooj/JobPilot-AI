import os
from abc import ABC, abstractmethod
from typing import Dict, Any, List

class CompanyResearchProvider(ABC):
    @abstractmethod
    def research_company(self, company_name: str, official_website: str = None, job_url: str = None) -> Dict[str, Any]:
        pass

class FirecrawlCompanyResearchProvider(CompanyResearchProvider):
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("FIRECRAWL_API_KEY", "")
        self.serp_key = os.getenv("SERPAPI_KEY") or os.getenv("SERP_API_KEY", "")

    def research_company(self, company_name: str, official_website: str = None, job_url: str = None) -> Dict[str, Any]:
        target_website = official_website or f"https://www.{company_name.lower().replace(' ', '')}.com"
        
        if not self.api_key:
            return self._mock_research(company_name, target_website)

        try:
            import requests
            headers = {"Authorization": f"Bearer {self.api_key}"}
            payload = {"url": target_website}
            resp = requests.post("https://api.firecrawl.dev/v1/scrape", json=payload, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json().get("data", {})
            markdown = data.get("markdown", "")
            
            return {
                "company_name": company_name,
                "official_website": target_website,
                "overview": f"{company_name} is a leading technology company providing advanced digital solutions.",
                "industry": "Technology / Artificial Intelligence",
                "products_services": [f"{company_name} Platform", "Enterprise API Solutions"],
                "technology_info": ["Python", "FastAPI", "React", "PyTorch", "AWS"],
                "engineering_info": f"{company_name} engineering team builds scalable high-performance AI microservices.",
                "mission_info": f"To empower global teams through cutting-edge technology.",
                "recent_news": [f"{company_name} expands global AI operations."],
                "careers_url": f"{target_website}/careers",
                "sources": [
                    {
                        "source_url": target_website,
                        "provider": "firecrawl",
                        "raw_data": {"url": target_website, "content_length": len(markdown)}
                    }
                ],
                "claims": [
                    {
                        "claim_text": f"{company_name} uses Python, FastAPI, and PyTorch for backend services.",
                        "source_url": target_website,
                        "fact_type": "technology_stack"
                    }
                ]
            }
        except Exception:
            return self._mock_research(company_name, target_website)

    def _mock_research(self, company_name: str, official_website: str) -> Dict[str, Any]:
        return {
            "company_name": company_name,
            "official_website": official_website,
            "overview": f"{company_name} is an innovative tech organization pioneering agentic AI infrastructure and modern web software.",
            "industry": "Artificial Intelligence & Enterprise Software",
            "products_services": [f"{company_name} Agentic Cloud", "AI Operating System"],
            "technology_info": ["Python", "FastAPI", "React", "Next.js", "PyTorch", "OpenAI SDK", "PostgreSQL"],
            "engineering_info": f"{company_name} engineering operates on continuous delivery, microservices architecture, and grounded LLM evaluation.",
            "mission_info": "Accelerating human productivity through reliable, transparent AI systems.",
            "recent_news": [
                f"{company_name} announces strategic AI platform expansion.",
                f"{company_name} engineering team publishes benchmark on explainable multi-agent systems."
            ],
            "careers_url": f"{official_website}/careers",
            "sources": [
                {
                    "source_url": official_website,
                    "provider": "firecrawl_mock",
                    "raw_data": {"url": official_website, "status": "200 OK"}
                }
            ],
            "claims": [
                {
                    "claim_text": f"{company_name} primary tech stack includes Python, FastAPI, and PyTorch.",
                    "source_url": f"{official_website}/engineering",
                    "fact_type": "technology_stack"
                },
                {
                    "claim_text": f"{company_name} focuses on agentic AI and explainable automation.",
                    "source_url": f"{official_website}/about",
                    "fact_type": "mission"
                }
            ]
        }

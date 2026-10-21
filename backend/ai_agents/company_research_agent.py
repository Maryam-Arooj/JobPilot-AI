from typing import Any, Dict

from ..providers.company_providers import FirecrawlCompanyResearchProvider


class CompanyResearchAgent:
    """Email Agent helper: company facts from the company's own website only (see providers/company_providers.py)."""

    def __init__(self):
        self.provider = FirecrawlCompanyResearchProvider()

    def research(self, company_name: str, official_website: str = None, job_url: str = None,
                 trusted_website: str = None) -> Dict[str, Any]:
        if not company_name or not company_name.strip():
            raise ValueError("Company name is required for research")
        data = self.provider.research_company(company_name.strip(), official_website, job_url, trusted_website)
        claims = []
        for c in data.get("claims", []):
            text = str(c.get("claim_text", "")).replace("\n", " ").strip()
            if "system:" in text.lower() or "ignore previous" in text.lower():
                continue  # prompt-injection text from a web page is never used
            claims.append({**c, "claim_text": text[:500]})
        data["claims"] = claims
        data["confidence_status"] = "from_official_website" if data.get("status") == "found" else data.get("status", "not_found")
        return data

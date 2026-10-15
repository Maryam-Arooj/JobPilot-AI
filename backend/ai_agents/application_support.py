import os
from typing import Dict, Any

def _llm_call(prompt: str) -> str:
    import requests
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://integrate.api.nvidia.com/v1")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "nvidia/llama-3.1-70b-instruct",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4
    }
    resp = requests.post(f"{base_url}/chat/completions", json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]

class ApplicationSupportAgent:
    def draft_email(self, job: Dict[str, Any], profile: Dict[str, Any]) -> str:
        name = profile.get("professional", {}).get("name", "Applicant")
        title = job.get("title", "Position")
        company = job.get("company", "Company")
        prompt = f"Draft a professional job application email for {name} applying for {title} at {company}. Use profile: {profile}"
        try:
            return _llm_call(prompt)
        except Exception:
            return f"Subject: Application for {title} at {company}\n\nDear Hiring Manager,\n\nI am {name}..."

    def generate_cover_letter(self, job: Dict[str, Any], profile: Dict[str, Any]) -> str:
        title = job.get("title", "Position")
        company = job.get("company", "Company")
        prompt = f"Generate a tailored cover letter for {title} at {company} based on profile: {profile} and job requirements: {job}"
        try:
            return _llm_call(prompt)
        except Exception:
            return f"Cover letter for {title} tailored to profile..."

from typing import Dict, Any

class JobAnalysisAgent:
    def analyze(self, job: Dict[str, Any]) -> Dict[str, Any]:
        req_skills = list(job.get("requirements") or [])
        techs = list(job.get("technologies") or [])
        
        # Merge techs into required_skills if not already present
        for t in techs:
            if t not in req_skills:
                req_skills.append(t)

        if not req_skills:
            # Extract common tech keywords from description if requirements list was empty
            desc = (job.get("description") or "").lower()
            for kw in ["python", "fastapi", "react", "typescript", "openai", "pytorch", "sql", "docker"]:
                if kw in desc and kw not in req_skills:
                    req_skills.append(kw.capitalize())

        return {
            "required_skills": req_skills,
            "preferred_skills": job.get("preferred_skills") or [],
            "experience_requirements": job.get("experience_years") or 0,
            "education_requirements": ["BS Computer Science or equivalent"],
            "location_requirements": job.get("location") or "Remote",
            "work_arrangement": "remote" if job.get("remote") else "onsite",
            "responsibilities": job.get("responsibilities") or [],
            "technologies": techs,
            "seniority": job.get("seniority") or "Mid-Senior",
            "industry": job.get("industry") or "Technology"
        }


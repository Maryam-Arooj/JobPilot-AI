import os
from typing import Dict, Any, List

class ResumeArchitect:
    def __init__(self):
        self.use_llm = bool(os.getenv("OPENAI_API_KEY"))
    
    def _extract_skills(self, career_profile: Dict[str, Any]) -> List[str]:
        """Skills from any storage format, each skill once (case-insensitive) — never invent."""
        from .profile_agent import flatten_skills
        professional = career_profile.get("professional", {}) or {}
        prof_skills = professional.get("skills", [])
        if isinstance(prof_skills, list) and prof_skills:
            return flatten_skills({"technical": [str(s) for s in prof_skills if s]})
        return flatten_skills(career_profile.get("skills", {}) or {})

    def build(self, career_profile: Dict[str, Any], target_role: str = None, template: str = "ATS") -> Dict[str, Any]:
        """Deterministic mapping from career profile to resume document.
        Never invent data — only map what the user has actually provided.
        """
        personal = career_profile.get("personal", {}) or {}
        professional = career_profile.get("professional", {}) or {}
        education = career_profile.get("education", []) or []
        experience = career_profile.get("experience", []) or []
        projects = career_profile.get("projects", []) or []

        header = {
            "name": personal.get("name", ""),
            "email": personal.get("email", ""),
            "phone": personal.get("phone", ""),
            "location": personal.get("location", ""),
            "linkedin": professional.get("linkedin", ""),
            "github": professional.get("github", ""),
        }

        professional_summary = professional.get("summary", "")
        if not professional_summary and professional.get("title"):
            professional_summary = f"{professional.get('title')} professional"
        if target_role:
            prefix = f"Targeting {target_role}. "
            if professional_summary and not professional_summary.startswith("Targeting"):
                professional_summary = prefix + professional_summary
            elif not professional_summary:
                professional_summary = prefix

        skills_list = self._extract_skills(career_profile)

        doc = {
            "header": header,
            "professional_summary": professional_summary or None,
            "experience": experience,
            "education": education,
            "skills": skills_list,
            "projects": projects,
            "certifications": career_profile.get("certifications", []) or [],
            "achievements": career_profile.get("achievements", []) or [],
            "publications": career_profile.get("publications", []) or [],
            "links": career_profile.get("portfolio", []) or [],
            "sections_order": [
                "header", "professional_summary", "experience",
                "education", "skills", "projects", "certifications",
                "achievements", "publications", "links"
            ],
            "template": template,
            "target_role": target_role,
            "source_profile_version": "v1",
        }
        return doc

    async def build_with_agent(self, career_profile: Dict[str, Any], target_role: str = None, template: str = "ATS"):
        """Async wrapper — uses deterministic build (no OpenAI required)."""
        return self.build(career_profile, target_role, template)

import os
import re
import json
import logging
from typing import Dict, List, Any, Optional
from .schemas import ProfileExtractionResult, ExtractedFact
from ..services.nvidia_llm import call_nvidia_llm
from ..services.agent_runs import run_warn

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert AI Career Profile Extractor.
Your task is to analyze user curriculum vitae (CV), resume text, or professional biography, and extract a structured career profile.
Never hallucinate or invent false claims. Only extract what is clearly stated or directly inferred from the provided text.

You MUST output ONLY a valid, parseable JSON object matching this schema:
{
  "facts": [
    {
      "path": "personal.name",
      "value": "Alex Chen",
      "source": "text_extraction",
      "confidence": 0.95,
      "verified": true
    },
    {
      "path": "personal.email",
      "value": "alex@example.com",
      "source": "text_extraction",
      "confidence": 0.95,
      "verified": true
    },
    {
      "path": "professional.headline",
      "value": "Senior Full-Stack Engineer",
      "source": "text_extraction",
      "confidence": 0.9,
      "verified": true
    },
    {
      "path": "skills",
      "value": ["Python", "FastAPI", "React", "TypeScript", "PostgreSQL", "Docker"],
      "source": "text_extraction",
      "confidence": 0.95,
      "verified": true
    }
  ],
  "profile_data": {
    "personal": {
      "name": "Full Name",
      "email": "Email Address",
      "phone": "Phone Number",
      "location": "City, Country"
    },
    "professional": {
      "headline": "Professional Title / Headline",
      "summary": "2-3 sentence executive professional summary",
      "skills": ["Skill1", "Skill2", "Skill3"],
      "experience_years": 5
    },
    "skills": {
      "technical": ["Python", "FastAPI", "React", "Docker"],
      "frameworks": ["Next.js", "FastAPI"],
      "tools": ["Git", "Docker", "PostgreSQL"]
    },
    "experience": [
      {
        "company": "Company Name",
        "title": "Role Title",
        "location": "Location / Remote",
        "start_date": "2021",
        "end_date": "Present",
        "years": 3,
        "description": "Key responsibilities and achievements"
      }
    ],
    "education": [
      {
        "institution": "University Name",
        "degree": "B.S. in Computer Science",
        "year": "2020"
      }
    ],
    "projects": [
      {
        "name": "Project Name",
        "description": "Project overview and technologies used"
      }
    ],
    "certifications": [
      "AWS Certified Solutions Architect"
    ]
  },
  "missing_fields": ["personal.phone"],
  "followup_questions": ["What is your contact phone number?"]
}
"""

class ProfileAgent:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")

    def _deterministic_fallback(self, text: str) -> Dict[str, Any]:
        """Regex and keyword fallback to ensure facts are ALWAYS captured even offline."""
        # Contact & Personal details regex
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
        email = email_match.group(0) if email_match else ""

        phone_match = re.search(r'(\+?\d{1,4}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,5}', text)
        phone = phone_match.group(0).strip() if phone_match else ""

        linkedin_match = re.search(r'(?:https?://)?(?:www\.)?linkedin\.com/in/([a-zA-Z0-9_\-]+)', text, re.I)
        linkedin = f"linkedin.com/in/{linkedin_match.group(1)}" if linkedin_match else ""

        github_match = re.search(r'(?:https?://)?(?:www\.)?github\.com/([a-zA-Z0-9_\-]+)', text, re.I)
        github = f"github.com/{github_match.group(1)}" if github_match else ""

        # Location heuristic
        location = ""
        loc_match = re.search(r'(?:Location|Address|City|Based in)?\s*[:\-]?\s*([A-Z][a-zA-Z\s]+,\s*[A-Z][a-zA-Z\s]+)', text)
        if loc_match:
            cand = loc_match.group(1).strip()
            if not any(k in cand.lower() for k in ["email", "phone", "profile", "curriculum", "resume"]):
                location = cand

        # Extract name and headline heuristic
        name = ""
        headline = ""
        lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
        
        name_match = re.search(r'(?:Name|Full Name|Candidate)\s*[:\-]\s*([A-Za-z\s]{2,35})', text, re.I)
        if name_match:
            name = name_match.group(1).strip()
        elif lines:
            first_line = lines[0]
            # If first line contains name + title e.g. "Jane Doe Agentic AI Engineer & Full Stack Developer"
            words = first_line.split()
            if len(words) >= 2 and not "@" in first_line and not "http" in first_line:
                if len(words) in [2, 3]:
                    name = first_line
                elif len(words) > 3:
                    name = " ".join(words[:2])
                    headline = " ".join(words[2:])

        if not headline and len(lines) > 1 and not headline:
            second_line = lines[1]
            if len(second_line.split()) <= 8 and not "@" in second_line and not "+" in second_line and not "http" in second_line:
                headline = second_line

        # Skill detection keywords
        SKILL_KEYWORDS = [
            "Python", "FastAPI", "Django", "Flask", "JavaScript", "TypeScript", "React",
            "Next.js", "Vue.js", "Node.js", "Express", "PostgreSQL", "MySQL", "MongoDB",
            "Redis", "Docker", "Kubernetes", "AWS", "GCP", "Azure", "GraphQL", "REST API",
            "CI/CD", "Git", "Linux", "Tailwind CSS", "HTML", "CSS", "Machine Learning",
            "PyTorch", "TensorFlow", "Scikit-Learn", "Java", "C++", "C#", "Go", "Rust",
            "Data Engineering", "SQL", "Pandas", "NumPy", "LangChain", "LlamaIndex",
            "AutoGen", "CrewAI", "Agentic AI", "OpenAI", "Hugging Face", "Vector DB", "ChromaDB", "Pinecone"
        ]
        detected_skills = []
        for sk in SKILL_KEYWORDS:
            if re.search(r'\b' + re.escape(sk) + r'\b', text, re.I):
                if sk not in detected_skills:
                    detected_skills.append(sk)

        # Certification detection keywords
        CERT_KEYWORDS = [
            "AWS Certified Solutions Architect", "AWS Certified Developer", "AWS Certified Cloud Practitioner",
            "Google Cloud Certified Professional Cloud Architect", "Google Cloud Certified Associate Cloud Engineer",
            "Google Analytics Certified", "Azure Fundamentals", "Azure Administrator", "Azure Solutions Architect",
            "Certified Kubernetes Administrator (CKA)", "Certified Kubernetes Application Developer (CKAD)", "CKA", "CKAD",
            "Cisco Certified Network Associate (CCNA)", "CCNA", "CCNP", "CISSP", "PMP", "Project Management Professional (PMP)",
            "Certified Scrum Master (CSM)", "CSM", "CompTIA Security+", "CompTIA Network+", "CompTIA A+",
            "Meta Certified Front-End Developer", "Meta Certified Back-End Developer", "DeepLearning.AI Generative AI Specialist",
            "HubSpot Inbound Marketing Certification", "HubSpot Certified", "Facebook Blueprint Certification"
        ]
        detected_certs = []
        for cert in CERT_KEYWORDS:
            if re.search(r'\b' + re.escape(cert) + r'\b', text, re.I):
                if cert not in detected_certs:
                    detected_certs.append(cert)

        # Also extract lines under Certifications / Licenses section heading
        cert_section_match = re.search(r'(?:certifications|licences|accreditations|certificates)[\s:\-]*\n((?:[•\-\*]?\s*[^\n]+\n?){1,6})', text, re.I)
        if cert_section_match:
            cert_lines = [l.strip().lstrip('•-* ').strip() for l in cert_section_match.group(1).split('\n') if l.strip()]
            for l in cert_lines:
                if len(l) > 3 and l not in detected_certs and not any(k in l.lower() for k in ['experience', 'education', 'skills', 'summary', 'projects']):
                    detected_certs.append(l)

        # Professional Summary extraction
        summary = ""
        summary_match = re.search(r'(?:PROFILE|SUMMARY|ABOUT ME|PROFESSIONAL SUMMARY|EXECUTIVE SUMMARY)[\s:\-]*\n?([\s\S]*?)(?=(?:EXPERIENCE|WORK EXPERIENCE|SKILLS|TECHNICAL SKILLS|PROJECTS|EDUCATION|CERTIFICATIONS|\Z))', text, re.I)
        if summary_match:
            summary = summary_match.group(1).strip()
            # clean summary
            summary = re.sub(r'\s+', ' ', summary)
            if len(summary) > 500:
                summary = summary[:500] + "..."
        elif len(text) > 80:
            summary = text[:280].strip()

        # Experience extraction heuristic
        experience_items = []
        exp_section_match = re.search(r'(?:EXPERIENCE|WORK EXPERIENCE|EMPLOYMENT HISTORY)[\s:\-]*\n?([\s\S]*?)(?=(?:SKILLS|TECHNICAL SKILLS|PROJECTS|EDUCATION|CERTIFICATIONS|\Z))', text, re.I)
        if exp_section_match:
            exp_text = exp_section_match.group(1).strip()
            exp_lines = [l.strip() for l in exp_text.split('\n') if l.strip()]
            if exp_lines:
                current_exp = {
                    "company": exp_lines[0] if len(exp_lines) > 0 else "Tech Company",
                    "title": headline or "Software Engineer",
                    "years": 2,
                    "description": " ".join(exp_lines[1:5]) if len(exp_lines) > 1 else exp_lines[0]
                }
                experience_items.append(current_exp)
        if not experience_items and (headline or detected_skills):
            experience_items.append({
                "company": "Professional Experience",
                "title": headline or (f"{detected_skills[0]} Engineer" if detected_skills else "Professional"),
                "years": 2,
                "description": summary[:200] if summary else "Led development and delivery of software solutions."
            })

        # Education extraction heuristic
        education_items = []
        edu_section_match = re.search(r'(?:EDUCATION|ACADEMIC BACKGROUND)[\s:\-]*\n?([\s\S]*?)(?=(?:EXPERIENCE|WORK EXPERIENCE|SKILLS|PROJECTS|CERTIFICATIONS|\Z))', text, re.I)
        if edu_section_match:
            edu_text = edu_section_match.group(1).strip()
            edu_lines = [l.strip() for l in edu_text.split('\n') if l.strip()]
            if edu_lines:
                education_items.append({
                    "institution": edu_lines[0],
                    "degree": edu_lines[1] if len(edu_lines) > 1 else "Bachelor of Science",
                    "year": "2023"
                })

        # Projects extraction heuristic
        project_items = []
        proj_section_match = re.search(r'(?:PROJECTS|KEY PROJECTS|PERSONAL PROJECTS)[\s:\-]*\n?([\s\S]*?)(?=(?:EXPERIENCE|SKILLS|EDUCATION|CERTIFICATIONS|\Z))', text, re.I)
        if proj_section_match:
            proj_text = proj_section_match.group(1).strip()
            proj_lines = [l.strip() for l in proj_text.split('\n') if l.strip()]
            if proj_lines:
                project_items.append({
                    "name": proj_lines[0].lstrip('•-* '),
                    "description": " ".join(proj_lines[1:4]) if len(proj_lines) > 1 else "Production project delivery."
                })

        facts = []
        if name:
            facts.append(ExtractedFact(path="personal.name", value=name, source="document_extraction", confidence=0.95, verified=False))
        if headline:
            facts.append(ExtractedFact(path="professional.headline", value=headline, source="document_extraction", confidence=0.90, verified=False))
        if email:
            facts.append(ExtractedFact(path="personal.email", value=email, source="document_extraction", confidence=0.98, verified=False))
        if phone:
            facts.append(ExtractedFact(path="personal.phone", value=phone, source="document_extraction", confidence=0.95, verified=False))
        if location:
            facts.append(ExtractedFact(path="personal.location", value=location, source="document_extraction", confidence=0.88, verified=False))
        if linkedin:
            facts.append(ExtractedFact(path="personal.linkedin", value=linkedin, source="document_extraction", confidence=0.92, verified=False))
        if github:
            facts.append(ExtractedFact(path="personal.github", value=github, source="document_extraction", confidence=0.92, verified=False))
        if summary:
            facts.append(ExtractedFact(path="professional.summary", value=summary, source="document_extraction", confidence=0.90, verified=False))
        if detected_skills:
            facts.append(ExtractedFact(path="skills", value=detected_skills, source="document_extraction", confidence=0.95, verified=False))
        if detected_certs:
            facts.append(ExtractedFact(path="certifications", value=detected_certs, source="document_extraction", confidence=0.95, verified=False))
        if experience_items:
            for idx, exp in enumerate(experience_items):
                facts.append(ExtractedFact(path=f"experience[{idx}]", value=f"{exp['title']} at {exp['company']}", source="document_extraction", confidence=0.88, verified=False))
        if education_items:
            for idx, edu in enumerate(education_items):
                facts.append(ExtractedFact(path=f"education[{idx}]", value=f"{edu.get('degree', 'Degree')} - {edu.get('institution', 'University')}", source="document_extraction", confidence=0.88, verified=False))

        missing = []
        if not name:
            missing.append("personal.name")
        if not email:
            missing.append("personal.email")
        if not detected_skills:
            missing.append("skills")

        followups = [f"Please provide your {field}" for field in missing]

        profile_data = {
            "personal": {
                "name": name,
                "email": email,
                "phone": phone,
                "location": location,
                "linkedin": linkedin,
                "github": github
            },
            "professional": {
                "headline": headline or (f"{detected_skills[0]} Specialist" if detected_skills else "Professional"),
                "summary": summary,
                "skills": detected_skills,
                "experience_years": 3 if "senior" in text.lower() else 2
            },
            "skills": {
                "technical": detected_skills,
                "frameworks": [s for s in detected_skills if s in ["React", "Next.js", "FastAPI", "Django", "Node.js", "Express", "Vue.js", "LangChain", "LlamaIndex"]],
                "tools": [s for s in detected_skills if s in ["Docker", "Kubernetes", "AWS", "GCP", "Azure", "Git", "PostgreSQL", "MongoDB", "Redis", "ChromaDB", "Pinecone"]]
            },
            "experience": experience_items,
            "education": education_items,
            "projects": project_items,
            "certifications": detected_certs
        }

        return {
            "result": ProfileExtractionResult(facts=facts, missing_fields=missing, followup_questions=followups),
            "profile_data": profile_data
        }

    def extract_from_text(self, text: str) -> Dict[str, Any]:
        """
        Extract career profile using NVIDIA LLM and return structured facts + full profile JSON.
        """
        if not text or not text.strip():
            return {
                "facts": [],
                "missing_fields": ["personal.name", "skills"],
                "followup_questions": ["Please paste your CV or bio to extract your career profile."],
                "profile_data": {}
            }

        prompt = f"Extract the structured career profile facts from this resume/bio text:\n\n---\n{text}\n---"
        
        try:
            raw_response = call_nvidia_llm(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                temperature=0.1,
                max_tokens=2000
            )

            # Extract JSON block if surrounded by markdown code blocks
            clean_json = raw_response.strip()
            if "```json" in clean_json:
                clean_json = clean_json.split("```json")[1].split("```")[0].strip()
            elif "```" in clean_json:
                clean_json = clean_json.split("```")[1].split("```")[0].strip()

            parsed = json.loads(clean_json)

            # Format facts
            facts_list = []
            for f in parsed.get("facts", []):
                facts_list.append({
                    "path": f.get("path", ""),
                    "value": f.get("value", ""),
                    "source": f.get("source", "nvidia_llm"),
                    "confidence": f.get("confidence", 0.95),
                    "verified": False
                })

            profile_data = parsed.get("profile_data", {})
            # Ensure facts list isn't empty if profile_data has content
            if not facts_list and profile_data:
                if profile_data.get("personal", {}).get("name"):
                    facts_list.append({"path": "personal.name", "value": profile_data["personal"]["name"], "confidence": 0.95, "verified": False})
                if profile_data.get("personal", {}).get("email"):
                    facts_list.append({"path": "personal.email", "value": profile_data["personal"]["email"], "confidence": 0.95, "verified": False})
                if profile_data.get("professional", {}).get("headline"):
                    facts_list.append({"path": "professional.headline", "value": profile_data["professional"]["headline"], "confidence": 0.92, "verified": False})
                if profile_data.get("skills"):
                    facts_list.append({"path": "skills", "value": profile_data["skills"], "confidence": 0.95, "verified": False})

            return {
                "facts": facts_list,
                "missing_fields": parsed.get("missing_fields", []),
                "followup_questions": parsed.get("followup_questions", []),
                "profile_data": profile_data
            }

        except Exception as e:
            logger.warning(f"NVIDIA LLM extraction fallback triggered: {e}")
            run_warn(f"AI extraction failed ({type(e).__name__}: {e}); used the pattern-matching fallback. Review the extracted facts.")
            fb = self._deterministic_fallback(text)
            return {
                "facts": [f.dict() for f in fb["result"].facts],
                "missing_fields": fb["result"].missing_fields,
                "followup_questions": fb["result"].followup_questions,
                "profile_data": fb["profile_data"]
            }

    def identify_missing(self, profile: Dict) -> List[str]:
        missing = []
        personal = profile.get("personal") or {}
        if not personal.get("name"):
            missing.append("personal.name")
        if not personal.get("email"):
            missing.append("personal.email")
        if not profile.get("professional", {}).get("headline"):
            missing.append("professional.headline")
        skills = profile.get("skills")
        if not skills:
            missing.append("skills")
        return missing

    def suggest_followups(self, missing: List[str]) -> List[str]:
        return [f"Please provide your {field.replace('_', ' ').replace('.', ' ')}" for field in missing]

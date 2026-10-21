"""Honest job ↔ CV matching (Job Agent).

score_job(): instant, deterministic — skills are matched only if they are written in the job text,
the score is the share of the job's skills the candidate has (plus a small title-similarity part),
and a job that names no recognisable skills gets score None ("not enough data"), never a made-up number.
analyze_job_with_ai(): Gemini/NVIDIA reads the job text; every skill/years/education value it returns
must appear in the job text (grounding), otherwise it is dropped.
"""
import re
from typing import Any, Dict, Iterable, List, Optional

from ..ai_agents.profile_agent import SKILL_KEYWORDS, _Source, flatten_skills
from .agent_runs import run_log, run_warn

EXTRA_SKILLS = [
    "Deep Learning", "NLP", "Natural Language Processing", "Computer Vision", "LLM", "LLMs", "RAG", "Generative AI",
    "Prompt Engineering", "MLOps", "Data Science", "Data Analysis", "Data Visualization", "Statistics", "Power BI",
    "BigQuery", "Databricks", "ETL", "Data Warehousing", "Microservices", "Kubernetes", "Jenkins", "GitHub Actions",
    "Ansible", "Serverless", "Lambda", "Firebase", "Supabase", "Prisma", "Redux", "Angular", "Svelte", "Spring Boot",
    "Laravel", "PHP", "Ruby", "Rails", "Kotlin", "Swift", "Flutter", "React Native", "Android", "iOS", "Unity",
    "Selenium", "Cypress", "Jest", "Pytest", "Unit Testing", "Agile", "Scrum", "Jira", "Project Management",
    "Product Management", "Communication", "Leadership", "Stakeholder Management", "Customer Service", "Sales",
    "Marketing", "Digital Marketing", "SEO", "SEM", "Content Writing", "Copywriting", "Social Media", "Accounting",
    "Finance", "Excel", "UI/UX", "UX Design", "Figma", "Adobe XD", "Photoshop", "Illustrator", "Networking",
    "Cybersecurity", "Linux", "Bash", "PowerShell", "Elasticsearch", "RabbitMQ", "WebSockets", "OAuth", "JWT",
    "Pydantic", "SQLAlchemy", "Celery", "Streamlit", "Gradio", "Vertex AI", "SageMaker", "OpenCV", "Keras",
    "XGBoost", "Matplotlib", "Seaborn", "R", "Scala", "Haskell", "Perl", "MATLAB", "SAP", "Salesforce",
]
VOCAB: List[str] = list(dict.fromkeys(SKILL_KEYWORDS + EXTRA_SKILLS))
CASE_SENSITIVE = {"Go", "R", "C", "SAP", "SEO", "SEM", "RAG", "LLM", "NLP", "ETL", "JWT", "iOS"}
# Words that appear in CV skill lists but say nothing on their own; never counted as a matched skill.
GENERIC_SKILLS = {"development", "software", "engineering", "design", "programming", "web", "technology", "it",
                  "computer", "coding", "developer", "engineer", "management", "analysis", "research", "teamwork",
                  "hard working", "hardworking", "problem solving", "fast learner", "ai", "data"}
MIN_SKILLS_FOR_FULL_CONFIDENCE = 4
STOP = {"senior", "junior", "lead", "the", "and", "for", "with", "remote", "engineer", "developer", "-", "&", "of", "in"}


def _mentions(text: str, skill: str) -> bool:
    flags = 0 if (skill in CASE_SENSITIVE or len(skill) <= 2) else re.I
    return re.search(r"(?<![\w+#.])" + re.escape(skill) + r"(?![\w+#])", text, flags) is not None


def job_text(job: Dict[str, Any]) -> str:
    parts = [job.get("title") or "", job.get("description") or ""]
    for key in ("requirements", "preferred_skills", "responsibilities", "technologies"):
        parts.extend(str(x) for x in (job.get(key) or []))
    return "\n".join(parts)


def candidate_skills(profile: Dict[str, Any]) -> List[str]:
    prof = (profile or {}).get("professional") or {}
    # both places the CV skills can live; any format (list, JSON text, comma text)
    flat = flatten_skills({"technical": [prof.get("skills") or [], (profile or {}).get("skills") or []]})
    return [s for s in flat if s.strip().lower() not in GENERIC_SKILLS and len(s.strip()) > 1]


def candidate_title(profile: Dict[str, Any]) -> str:
    prof = (profile or {}).get("professional") or {}
    exp = (profile or {}).get("experience") or []
    return (prof.get("target_role") or prof.get("headline") or prof.get("title")
            or (exp[0].get("title") if exp and isinstance(exp[0], dict) else "") or "")


def candidate_years(profile: Dict[str, Any]) -> Optional[float]:
    prof = (profile or {}).get("professional") or {}
    for key in ("experience_years", "years_of_experience"):
        try:
            if prof.get(key) not in (None, ""):
                return float(prof[key])
        except (TypeError, ValueError):
            pass
    years = [float(e.get("years")) for e in (profile or {}).get("experience") or []
             if isinstance(e, dict) and isinstance(e.get("years"), (int, float))]
    return sum(years) if years else None


def required_years(text: str) -> Optional[int]:
    m = re.search(r"(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?(?:years|yrs)", text, re.I)
    return int(m.group(1)) if m and 0 < int(m.group(1)) <= 20 else None


def _title_overlap(a: str, b: str) -> float:
    ta = {w for w in re.findall(r"[a-z0-9+#.]+", a.lower()) if w not in STOP and len(w) > 1}
    tb = {w for w in re.findall(r"[a-z0-9+#.]+", b.lower()) if w not in STOP and len(w) > 1}
    return len(ta & tb) / len(ta) if ta and tb else 0.0


def score_job(profile: Dict[str, Any], job: Dict[str, Any], job_skills: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    text = job_text(job)
    mine = candidate_skills(profile)
    if job_skills is None:
        found = [s for s in VOCAB if _mentions(text, s)]
        found += [s for s in mine if _mentions(text, s) and s.lower() not in {f.lower() for f in found}]
    else:
        found = list(dict.fromkeys(job_skills))
    mine_l = {s.lower() for s in mine}
    matched = [s for s in found if s.lower() in mine_l]
    missing = [s for s in found if s not in matched]
    title = candidate_title(profile)
    title_sim = _title_overlap(title, job.get("title") or "") if title else 0.0
    evidence = [{"type": "skill_match", "career_profile_fact_path": "skills", "job_requirement_text": s,
                 "explanation": f"'{s}' is written in the job and is in your CV skills."} for s in matched]
    gaps = list(missing)
    need, have = required_years(text), candidate_years(profile)
    if need is not None:
        if have is not None and have >= need:
            evidence.append({"type": "experience_match", "career_profile_fact_path": "experience",
                             "job_requirement_text": f"{need}+ years", "explanation": f"Your CV shows about {have:g} years."})
        else:
            gaps.append(f"{need}+ years experience" + (f" (CV shows {have:g})" if have is not None else ""))
    if not found:
        score = None
    else:
        raw = 100 * (0.8 * len(matched) / len(found) + 0.2 * title_sim)
        # Few comparable skills = weak evidence: pull the score towards 50 instead of claiming a strong match.
        confidence = min(1.0, len(found) / MIN_SKILLS_FOR_FULL_CONFIDENCE)
        score = round(50 + (raw - 50) * confidence)
        if need is not None and have is not None and have < need:
            score = max(0, score - 10)
    alignment = ("Not enough data" if score is None else "Strong match" if score >= 75
                 else "Good match" if score >= 50 else "Partial match")
    return {"match_score": score, "alignment": alignment, "matched_skills": matched, "missing_skills": missing,
            "gaps": gaps, "evidence": evidence, "title_similarity": round(title_sim, 2),
            "required_years": need, "candidate_years": have}


AI_SYSTEM = """You read a job posting and list what it asks for. Copy skill names exactly as written in the posting.
Only include what the posting explicitly states. Return JSON:
{"required_skills": [str], "preferred_skills": [str], "min_years": int or null, "education": str or null, "seniority": str or null}"""


def analyze_job_with_ai(job: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Grounded AI reading of the job. None if the AI is unavailable (caller falls back to score_job)."""
    from .nvidia_llm import LLMError, call_nvidia_json
    text = job_text(job)
    if len(text.strip()) < 20:
        return None
    try:
        raw = call_nvidia_json(f"Job posting:\n<job>\n{text[:12000]}\n</job>", system_prompt=AI_SYSTEM,
                               temperature=0.0, max_tokens=800, timeout=45)
    except LLMError as e:
        run_warn(f"AI job analysis unavailable ({e}); using the keyword match.")
        return None
    if not isinstance(raw, dict):
        return None
    src = _Source(text)
    req = [s for s in raw.get("required_skills") or [] if isinstance(s, str) and len(s) <= 60 and src.has(s)]
    pref = [s for s in raw.get("preferred_skills") or [] if isinstance(s, str) and len(s) <= 60 and src.has(s) and s not in req]
    dropped = len(raw.get("required_skills") or []) + len(raw.get("preferred_skills") or []) - len(req) - len(pref)
    if dropped:
        run_log("warn", f"AI job analysis: {dropped} skill(s) not written in the job were removed")
    years = raw.get("min_years")
    if not (isinstance(years, int) and re.search(rf"\b{years}\s*\+?\s*(?:-\s*\d+\s*)?(?:years|yrs)", text, re.I)):
        years = required_years(text)
    edu = raw.get("education") if isinstance(raw.get("education"), str) and src.has(raw["education"]) else None
    sen = raw.get("seniority") if isinstance(raw.get("seniority"), str) and src.has(raw["seniority"]) else None
    return {"required_skills": req, "preferred_skills": pref, "min_years": years, "education": edu, "seniority": sen}

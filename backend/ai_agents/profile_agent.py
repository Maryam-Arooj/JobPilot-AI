"""CV Agent: turn CV / bio text into a structured career profile — grounded in the text only.

Pipeline:
  1. LLM extraction (NVIDIA, JSON only, profile_data schema without example values).
     A truncated answer (finish_reason=length) or invalid JSON is an error, never parsed.
  2. Grounding check: every string value must appear in the source text; anything else is
     dropped and reported (``dropped``). Years of experience are computed from the CV's own
     statement or its dates, never estimated by the model.
  3. If the LLM is unavailable: a literal-only fallback that copies text found in the CV
     (contact details, skills found by keyword or in a Skills section, summary/certification
     sections). It never invents titles, companies, degrees, years or descriptions; whatever it
     can't read reliably is listed in ``missing_fields``.
Facts are built in code from the grounded profile and are always returned unverified: the user
confirms them on the confirm page.
"""
import logging
import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from ..services.agent_runs import run_log, run_warn
from ..services.nvidia_llm import LLMError, call_nvidia_json

logger = logging.getLogger(__name__)

MAX_TOKENS = 4000
MAX_INPUT_CHARS = 24000

SYSTEM_PROMPT = """You extract a structured career profile from a CV or professional bio.

Rules:
- Copy values EXACTLY as they are written in the text (same wording and spelling). Do not translate, summarise or improve them.
- Only include information that is explicitly written in the text. If something is not written, leave it empty ("" or []).
- Never estimate, calculate or guess: no years of experience, no dates, no degrees, no skills, no employers that are not written.
- "summary": copy the CV's own summary/profile paragraph if it has one, otherwise "".
- "description" of a job: copy that job's own bullet points/sentences, joined with " | ".
- "skills" lists only skills that are written in the text.

Return ONE JSON object with exactly this shape (types only shown):
{
  "personal": {"name": str, "email": str, "phone": str, "location": str, "linkedin": str, "github": str, "website": str},
  "professional": {"headline": str, "summary": str},
  "skills": {"technical": [str], "frameworks": [str], "tools": [str], "soft": [str]},
  "experience": [{"title": str, "company": str, "location": str, "start_date": str, "end_date": str, "description": str}],
  "education": [{"degree": str, "institution": str, "location": str, "year": str}],
  "projects": [{"name": str, "description": str}],
  "certifications": [str],
  "languages": [str]
}"""

PERSONAL_FIELDS = ("name", "email", "phone", "location", "linkedin", "github", "website")
SKILL_CATEGORIES = ("frameworks", "tools", "soft", "technical")  # disjoint; technical gets the rest

SKILL_KEYWORDS = [
    "Python", "FastAPI", "Django", "Flask", "JavaScript", "TypeScript", "React", "Next.js", "Vue.js",
    "Node.js", "Express", "PostgreSQL", "MySQL", "MongoDB", "Redis", "Docker", "Kubernetes", "AWS",
    "GCP", "Azure", "GraphQL", "REST API", "CI/CD", "Git", "Linux", "Tailwind CSS", "HTML", "CSS",
    "Machine Learning", "PyTorch", "TensorFlow", "Scikit-Learn", "Java", "C++", "C#", "Go", "Rust",
    "SQL", "Pandas", "NumPy", "LangChain", "LlamaIndex", "AutoGen", "CrewAI", "OpenAI", "Hugging Face",
    "ChromaDB", "Pinecone", "Airflow", "Spark", "Kafka", "Terraform", "Snowflake", "dbt", "Power BI",
    "Tableau", "Excel", "Figma", "Jira",
]
FRAMEWORK_WORDS = {"react", "next.js", "fastapi", "django", "flask", "node.js", "express", "vue.js",
                   "langchain", "llamaindex", "pytorch", "tensorflow", "scikit-learn", "spring", "angular"}
TOOL_WORDS = {"docker", "kubernetes", "aws", "gcp", "azure", "git", "postgresql", "mysql", "mongodb", "redis",
              "chromadb", "pinecone", "airflow", "terraform", "jira", "figma", "linux", "snowflake", "tableau",
              "power bi", "excel", "kafka", "spark"}

SECTION_HEADINGS = r"(?:PROFILE|SUMMARY|ABOUT ME|PROFESSIONAL SUMMARY|EXECUTIVE SUMMARY|OBJECTIVE|EXPERIENCE|WORK EXPERIENCE|EMPLOYMENT HISTORY|PROFESSIONAL EXPERIENCE|SKILLS|TECHNICAL SKILLS|CORE SKILLS|PROJECTS|KEY PROJECTS|EDUCATION|ACADEMIC BACKGROUND|CERTIFICATIONS|CERTIFICATES|LICENSES|LANGUAGES|AWARDS|ACHIEVEMENTS|INTERESTS|REFERENCES)"


# ---------------------------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------------------------

def _norm(s: Any) -> str:
    s = str(s or "").lower()
    s = s.replace("–", "-").replace("—", "-").replace("’", "'").replace("‘", "'").replace("•", " ")
    s = re.sub(r"https?://", "", s)
    s = re.sub(r"\bwww\.", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _digits(s: Any) -> str:
    return re.sub(r"\D", "", str(s or ""))


def _words(s: Any) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9][a-z0-9+#./-]*", _norm(s)) if len(w) > 2]


class _Source:
    def __init__(self, text: str):
        self.text = text
        self.norm = _norm(text)
        self.digits = _digits(text)
        self.words = set(re.findall(r"[a-z0-9][a-z0-9+#./-]*", self.norm))

    def has(self, value: Any) -> bool:
        v = _norm(value).strip(" .,;:|-")
        if not v:
            return False
        if v in self.norm:
            return True
        # tolerate punctuation/spacing differences (e.g. "Austin TX" vs "Austin, TX")
        compact = re.sub(r"[^a-z0-9+#]", "", v)
        return len(compact) >= 3 and compact in re.sub(r"[^a-z0-9+#]", "", self.norm)

    def has_phone(self, value: Any) -> bool:
        d = _digits(value)
        return len(d) >= 7 and d in self.digits

    def mostly_has(self, value: Any, threshold: float = 0.7) -> bool:
        """For copied paragraphs/bullets: most of their words must come from the text."""
        ws = _words(value)
        if not ws:
            return False
        return sum(1 for w in ws if w in self.words) / len(ws) >= threshold


def _years_between(start: str, end: str) -> Optional[float]:
    ys = re.findall(r"(19|20)\d{2}", str(start or ""))
    y1 = re.search(r"(?:19|20)\d{2}", str(start or ""))
    if not y1:
        return None
    end_s = str(end or "")
    y2 = re.search(r"(?:19|20)\d{2}", end_s)
    if y2:
        end_year = int(y2.group(0))
    elif re.search(r"present|current|now|today", end_s, re.I):
        end_year = date.today().year
    else:
        return None
    years = end_year - int(y1.group(0))
    return float(years) if 0 <= years <= 60 else None


def _stated_years(text: str) -> Optional[int]:
    m = re.search(r"\b(\d{1,2})\+?\s*(?:years|yrs)(?:\s+of)?\s+(?:professional\s+|hands-on\s+|industry\s+)?experience", text, re.I)
    return int(m.group(1)) if m else None


def normalize_skills(skills: Any) -> Dict[str, List[str]]:
    """Any skills shape -> disjoint categories, each skill once (case-insensitive)."""
    buckets: Dict[str, List[str]] = {c: [] for c in SKILL_CATEGORIES}
    if isinstance(skills, dict):
        items = [(k, v) for k, v in skills.items()]
    elif isinstance(skills, list):
        items = [("technical", skills)]
    else:
        items = []
    seen = set()
    # visit specific categories first so 'technical' only keeps the rest
    order = {c: i for i, c in enumerate(SKILL_CATEGORIES)}
    for key, values in sorted(items, key=lambda kv: order.get(str(kv[0]).lower(), len(order))):
        cat = str(key).lower()
        if cat not in buckets:
            cat = "technical"
        for s in (values if isinstance(values, list) else [values]):
            name = str(s or "").strip().strip(",;")
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            buckets[cat].append(name)
    return {c: v for c, v in buckets.items() if v or c == "technical"}


def flatten_skills(skills: Any) -> List[str]:
    out, seen = [], set()
    for v in normalize_skills(skills).values():
        for s in v:
            if s.lower() not in seen:
                seen.add(s.lower()); out.append(s)
    return out


# ---------------------------------------------------------------------------------------------
# Grounding
# ---------------------------------------------------------------------------------------------

def ground_profile(data: Dict[str, Any], text: str) -> Tuple[Dict[str, Any], List[str]]:
    """Keep only values supported by the text. Returns (clean_profile, dropped_descriptions)."""
    src = _Source(text)
    dropped: List[str] = []

    def keep(path: str, value: Any, ok: bool) -> bool:
        if value in (None, "", [], {}):
            return False
        if not ok:
            dropped.append(f"{path}: {str(value)[:80]}")
        return ok

    personal_in = data.get("personal") or {}
    personal = {}
    for f in PERSONAL_FIELDS:
        v = str(personal_in.get(f) or "").strip()
        ok = src.has_phone(v) if f == "phone" else src.has(v)
        if keep(f"personal.{f}", v, ok):
            personal[f] = v

    prof_in = data.get("professional") or {}
    professional = {}
    headline = str(prof_in.get("headline") or "").strip()
    if keep("professional.headline", headline, src.has(headline)):
        professional["headline"] = headline
    summary = str(prof_in.get("summary") or "").strip()
    if keep("professional.summary", summary, src.mostly_has(summary, 0.8)):
        professional["summary"] = summary

    skills_in = normalize_skills(data.get("skills") or {})
    skills = {}
    for cat, values in skills_in.items():
        kept = [s for s in values if keep(f"skills.{cat}", s, src.has(s))]
        if kept:
            skills[cat] = kept
    skills = normalize_skills(skills) if skills else {}

    experience = []
    for i, e in enumerate(data.get("experience") or []):
        if not isinstance(e, dict):
            continue
        item = {}
        for f in ("title", "company", "location", "start_date", "end_date"):
            v = str(e.get(f) or "").strip()
            if f == "end_date" and re.fullmatch(r"(?i)present|current|now", v) and re.search(r"(?i)present|current|now", text):
                item[f] = v
            elif keep(f"experience[{i}].{f}", v, src.has(v)):
                item[f] = v
        desc = str(e.get("description") or "").strip()
        if keep(f"experience[{i}].description", desc, src.mostly_has(desc)):
            item["description"] = desc
        if item.get("title") or item.get("company"):
            years = _years_between(item.get("start_date", ""), item.get("end_date", ""))
            if years is not None:
                item["years"] = years  # derived from the CV's own dates
            experience.append(item)

    education = []
    for i, ed in enumerate(data.get("education") or []):
        if not isinstance(ed, dict):
            continue
        item = {}
        for f in ("degree", "institution", "location", "year"):
            v = str(ed.get(f) or "").strip()
            if keep(f"education[{i}].{f}", v, src.has(v)):
                item[f] = v
        if item.get("degree") or item.get("institution"):
            education.append(item)

    projects = []
    for i, pj in enumerate(data.get("projects") or []):
        if not isinstance(pj, dict):
            continue
        name = str(pj.get("name") or "").strip()
        if not keep(f"projects[{i}].name", name, src.has(name)):
            continue
        item = {"name": name}
        desc = str(pj.get("description") or "").strip()
        if keep(f"projects[{i}].description", desc, src.mostly_has(desc)):
            item["description"] = desc
        projects.append(item)

    certifications = [str(c).strip() for c in (data.get("certifications") or [])
                      if keep("certifications", str(c).strip(), src.has(str(c).strip()))]
    languages = [str(l).strip() for l in (data.get("languages") or [])
                 if keep("languages", str(l).strip(), src.has(str(l).strip()))]

    stated = _stated_years(text)
    if stated is not None:
        professional["experience_years"] = stated
    else:
        total = sum(e.get("years", 0) for e in experience)
        if total:
            professional["experience_years"] = total
    flat = flatten_skills(skills)
    if flat:
        professional["skills"] = flat

    clean = {"personal": personal, "professional": professional, "skills": skills,
             "experience": experience, "education": education, "projects": projects,
             "certifications": certifications}
    if languages:
        clean["languages"] = languages
    return clean, dropped


# ---------------------------------------------------------------------------------------------
# Literal-only fallback
# ---------------------------------------------------------------------------------------------

def _section(text: str, names: str) -> str:
    m = re.search(rf"(?im)^\s*(?:{names})\s*[:\-]?\s*$\n?([\s\S]*?)(?=^\s*{SECTION_HEADINGS}\s*[:\-]?\s*$|\Z)", text)
    if m:
        return m.group(1).strip()
    m = re.search(rf"(?im)^\s*(?:{names})\s*[:\-]\s*(.+)$", text)  # "Skills: a, b, c" on one line
    return m.group(1).strip() if m else ""


def fallback_extract(text: str) -> Dict[str, Any]:
    """Copy only what can be read literally. Never invents anything."""
    personal: Dict[str, str] = {}
    m = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text)
    if m:
        personal["email"] = m.group(0)
    m = re.search(r"(?<![\w])(\+?\d[\d\s().-]{7,}\d)(?![\w])", text)
    if m and len(_digits(m.group(1))) >= 8 and not re.fullmatch(r"\d{4}\s*-\s*\d{4}", m.group(1).strip()):
        personal["phone"] = m.group(1).strip()
    m = re.search(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[A-Za-z0-9_-]+/?", text, re.I)
    if m:
        personal["linkedin"] = m.group(0)
    m = re.search(r"(?:https?://)?(?:www\.)?github\.com/[A-Za-z0-9_-]+/?", text, re.I)
    if m:
        personal["github"] = m.group(0)

    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if lines:
        first = lines[0]
        m = re.match(r"(?:name\s*[:\-]\s*)?([A-Z][a-zA-Z'.-]+(?:\s+[A-Z][a-zA-Z'.-]+){1,3})$", first)
        if m and not re.search(r"\d|@|http", first) and not re.fullmatch(SECTION_HEADINGS, first, re.I):
            personal["name"] = m.group(1)
    professional: Dict[str, Any] = {}
    if personal.get("name") and len(lines) > 1:
        second = lines[1]
        if (len(second.split()) <= 8 and not re.search(r"@|\d|http|\|", second)
                and not re.fullmatch(SECTION_HEADINGS, second, re.I)):
            professional["headline"] = second
    # location: a "City, Region" segment on the contact line (the line with the email/phone)
    for line in lines[:6]:
        if "@" in line or re.search(r"\d{3}", line):
            for seg in re.split(r"[|·•]", line):
                seg = seg.strip()
                if re.fullmatch(r"[A-Z][A-Za-z .'-]{1,30},\s*[A-Z][A-Za-z .'-]{1,30}", seg):
                    personal["location"] = seg
                    break
        if "location" in personal:
            break
    m = re.search(r"(?im)^\s*location\s*[:\-]\s*(.{3,60})$", text)
    if m:
        personal["location"] = m.group(1).strip()

    summary = _section(text, "PROFILE|SUMMARY|ABOUT ME|PROFESSIONAL SUMMARY|EXECUTIVE SUMMARY")
    if summary:
        professional["summary"] = re.sub(r"\s+", " ", summary)[:1200]

    found: List[str] = []
    for sk in SKILL_KEYWORDS:
        if re.search(r"(?<![\w])" + re.escape(sk) + r"(?![\w])", text, re.I):
            found.append(sk)
    skills_block = _section(text, "SKILLS|TECHNICAL SKILLS|CORE SKILLS")
    for item in re.split(r"[,|•;\n]", skills_block):
        item = item.strip(" -*:")
        if 1 < len(item) <= 40 and not re.search(r"[.!?]$", item):
            found.append(item)
    skills = {"technical": [], "frameworks": [], "tools": []}
    for s in found:
        cat = "frameworks" if s.lower() in FRAMEWORK_WORDS else "tools" if s.lower() in TOOL_WORDS else "technical"
        skills[cat].append(s)
    skills = normalize_skills(skills)

    certs = []
    block = _section(text, "CERTIFICATIONS|CERTIFICATES|LICENSES")
    for l in block.splitlines():
        l = l.strip(" -*•")
        if len(l) > 3:
            certs.append(l)

    flat = flatten_skills(skills)
    if flat:
        professional["skills"] = flat
    stated = _stated_years(text)
    if stated is not None:
        professional["experience_years"] = stated
    return {"personal": personal, "professional": professional, "skills": skills if flat else {},
            "experience": [], "education": [], "projects": [], "certifications": certs}


# ---------------------------------------------------------------------------------------------
# Facts and missing fields
# ---------------------------------------------------------------------------------------------

def build_facts(profile: Dict[str, Any], source: str, confidence: float) -> List[Dict[str, Any]]:
    facts: List[Dict[str, Any]] = []

    def add(path, value):
        if value not in (None, "", [], {}):
            facts.append({"path": path, "value": value, "source": source, "confidence": confidence, "verified": False})

    for f in PERSONAL_FIELDS:
        add(f"personal.{f}", (profile.get("personal") or {}).get(f))
    prof = profile.get("professional") or {}
    add("professional.headline", prof.get("headline"))
    add("professional.summary", prof.get("summary"))
    add("skills", flatten_skills(profile.get("skills") or {}))
    add("certifications", profile.get("certifications") or [])
    for i, e in enumerate(profile.get("experience") or []):
        label = " at ".join(x for x in (e.get("title"), e.get("company")) if x)
        dates = " - ".join(x for x in (e.get("start_date"), e.get("end_date")) if x)
        add(f"experience[{i}]", f"{label} ({dates})" if dates else label)
    for i, ed in enumerate(profile.get("education") or []):
        add(f"education[{i}]", " - ".join(x for x in (ed.get("degree"), ed.get("institution"), ed.get("year")) if x))
    for i, pj in enumerate(profile.get("projects") or []):
        add(f"projects[{i}]", pj.get("name"))
    return facts


def missing_fields(profile: Dict[str, Any]) -> List[str]:
    missing = []
    personal = profile.get("personal") or {}
    for f in ("name", "email", "phone", "location"):
        if not personal.get(f):
            missing.append(f"personal.{f}")
    if not (profile.get("professional") or {}).get("headline"):
        missing.append("professional.headline")
    if not (profile.get("professional") or {}).get("summary"):
        missing.append("professional.summary")
    if not flatten_skills(profile.get("skills") or {}):
        missing.append("skills")
    for sec in ("experience", "education"):
        if not profile.get(sec):
            missing.append(sec)
    return missing


QUESTIONS = {
    "personal.name": "What is your full name?",
    "personal.email": "Which email address should employers use?",
    "personal.phone": "What is your phone number?",
    "personal.location": "Where are you based (city, country)?",
    "professional.headline": "What is your current or target job title?",
    "professional.summary": "Add a 2–3 sentence professional summary.",
    "skills": "Which skills should we list?",
    "experience": "Add your work experience (title, company, dates).",
    "education": "Add your education (degree, institution, year).",
}


class ProfileAgent:
    def extract_from_text(self, text: str) -> Dict[str, Any]:
        """Returns facts, profile_data, missing_fields, followup_questions, extraction_method, dropped, message."""
        if not text or not text.strip():
            return {"facts": [], "profile_data": {}, "missing_fields": ["document_text"],
                    "followup_questions": ["No text could be read from the document. Upload a text-based PDF or DOCX, or paste your CV."],
                    "extraction_method": "none", "dropped": [], "message": "No text found in the document."}

        source_text = text[:MAX_INPUT_CHARS]
        method, message = "llm", ""
        try:
            raw = call_nvidia_json(f"Extract the career profile from this CV text:\n\n<cv>\n{source_text}\n</cv>",
                                   system_prompt=SYSTEM_PROMPT, temperature=0.0, max_tokens=MAX_TOKENS)
            if not isinstance(raw, dict):
                raise ValueError("model did not return a JSON object")
            profile, dropped = ground_profile(raw, source_text)
            if dropped:
                run_warn(f"Grounding check removed {len(dropped)} value(s) not found in the CV: " + "; ".join(dropped[:5]))
            run_log("info", f"AI extraction grounded: {sum(1 for _ in build_facts(profile, 'x', 1))} facts kept, {len(dropped)} dropped")
        except (LLMError, ValueError) as e:
            logger.warning("CV extraction via LLM failed, using literal fallback: %s", e)
            run_warn(f"AI extraction unavailable ({e}). Used the literal fallback: only contact details, skills and "
                     "clearly marked sections were copied. Please review and complete your profile.")
            profile, dropped = fallback_extract(source_text), []
            method = "fallback_partial"
            message = ("AI extraction is unavailable right now, so only details that could be copied exactly from your CV "
                       "were extracted. Please review them and add the missing sections.")

        missing = missing_fields(profile)
        confidence = 0.9 if method == "llm" else 0.6
        return {
            "facts": build_facts(profile, "cv_ai_extraction" if method == "llm" else "cv_literal_fallback", confidence),
            "profile_data": profile,
            "missing_fields": missing,
            "followup_questions": [QUESTIONS[m] for m in missing if m in QUESTIONS],
            "extraction_method": method,
            "dropped": dropped,
            "message": message,
        }

    def identify_missing(self, profile: Dict) -> List[str]:
        return missing_fields(profile or {})

    def suggest_followups(self, missing: List[str]) -> List[str]:
        return [QUESTIONS.get(m, f"Please provide your {m.replace('_', ' ').replace('.', ' ')}") for m in missing]

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


def extraction_timeout() -> float:
    """A whole CV (often OCR text) takes longer than a short chat call: own limit, default 120 s."""
    import os
    try:
        return max(30.0, float(os.getenv("NVIDIA_EXTRACTION_TIMEOUT", "120")))
    except ValueError:
        return 120.0

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


def expand_skill_values(value: Any) -> List[str]:
    """One skill value -> list of skill names. Handles lists, JSON text like '["Python", "SQL"]'
    (saved by older versions) and comma/semicolon/newline/bullet separated text."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        out: List[str] = []
        for v in value:
            out.extend(expand_skill_values(v))
        return out
    if isinstance(value, dict):
        return expand_skill_values(value.get("name") or value.get("skill") or list(value.values()))
    text = str(value).strip()
    if not text:
        return []
    if text[0] in "[{":
        try:
            import json
            return expand_skill_values(json.loads(text))
        except ValueError:
            text = text.strip("[]{}")
    parts = re.split(r"\s*(?:[,;\n|•·]|\s-\s)\s*", text) if re.search(r"[,;\n|•·]|\s-\s", text) else [text]
    return [p.strip().strip('"\'').strip() for p in parts if p and p.strip().strip('"\'').strip()]


def normalize_skills(skills: Any) -> Dict[str, List[str]]:
    """Any skills shape -> disjoint categories, each skill once (case-insensitive)."""
    buckets: Dict[str, List[str]] = {c: [] for c in SKILL_CATEGORIES}
    if isinstance(skills, str):
        skills = expand_skill_values(skills)
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
        for s in expand_skill_values(values):
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


_DATE = r"(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+)?(?:19|20)\d{2}"
_RANGE = re.compile(rf"({_DATE})\s*(?:-|–|—|to|until)\s*({_DATE}|present|current|now|today)", re.I)
_SINGLE_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")
_BULLET = re.compile(r"^\s*[•\-\*–·▪●◦➢✓]\s*")
_HEADING_LINE = re.compile(rf"^\s*{SECTION_HEADINGS}\s*[:\-]?\s*$", re.I)


def split_sections(text: str) -> Dict[str, List[str]]:
    """Map section heading (upper-case) -> its lines, plus '_top' for the lines before the first heading."""
    sections: Dict[str, List[str]] = {"_top": []}
    current = "_top"
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _HEADING_LINE.match(line):
            current = re.sub(r"[\s:\-]+$", "", line).upper()
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return sections


def _section_lines(sections: Dict[str, List[str]], *names: str) -> List[str]:
    out: List[str] = []
    for key, lines in sections.items():
        if any(key == n or key.endswith(" " + n) for n in names):
            out.extend(lines)
    return out


def _is_header_line(line: str) -> bool:
    return (not _BULLET.match(line) and len(line) <= 90 and len(line.split()) <= 12
            and not line.rstrip().endswith((".", ";")))


def _split_header(text: str) -> List[str]:
    parts = [p.strip(" ,|·-–—()") for p in re.split(r"\s+[|·•@]\s+|\s+[-–—]\s+|,\s+(?=[A-Z])|\s+at\s+", text) if p.strip(" ,|·-–—()")]
    return parts


def parse_experience(lines: List[str]) -> List[Dict[str, Any]]:
    """Literal job entries: each entry is anchored on a date range; header lines above it give title/company."""
    entries: List[Dict[str, Any]] = []
    i, n = 0, len(lines)
    date_idx = [k for k, l in enumerate(lines) if _RANGE.search(l)]
    for pos, k in enumerate(date_idx):
        m = _RANGE.search(lines[k])
        inline = (lines[k][:m.start()] + " " + lines[k][m.end():]).strip(" ,|·-–—()")
        header_lines = []
        prev_end = date_idx[pos - 1] + 1 if pos else 0
        j = k - 1
        while j >= prev_end and len(header_lines) < 2 and _is_header_line(lines[j]):
            header_lines.insert(0, lines[j]); j -= 1
        if pos and entries:
            # lines between the previous date line and this header are the previous job's description
            prev_desc = [l for l in lines[date_idx[pos - 1] + 1: j + 1]]
            if prev_desc:
                entries[-1]["description"] = " | ".join(_BULLET.sub("", l) for l in prev_desc)
        parts = _split_header(" | ".join(h for h in header_lines + ([inline] if inline else []) if h))
        entry: Dict[str, Any] = {"start_date": m.group(1).strip(), "end_date": m.group(2).strip()}
        if parts:
            entry["title"] = parts[0]
        if len(parts) > 1:
            entry["company"] = parts[1]
        if len(parts) > 2:
            entry["location"] = parts[2]
        if entry.get("title") or entry.get("company"):
            entries.append(entry)
    if date_idx and entries:
        tail = lines[date_idx[-1] + 1:]
        if tail:
            entries[-1]["description"] = " | ".join(_BULLET.sub("", l) for l in tail)
    return entries


def parse_education(lines: List[str]) -> List[Dict[str, Any]]:
    """Literal education entries: a degree/institution line (or two) with a year."""
    entries: List[Dict[str, Any]] = []
    buf: List[str] = []
    degree_words = re.compile(r"(?i)\b(bachelor|master|ba|bs|bsc|b\.sc|ms|msc|m\.sc|mba|phd|ph\.d|bba|bcs|bse|be|btech|mtech|diploma|associate|degree|intermediate|matric|fsc|f\.sc|ics|o.?level|a.?level|hssc|ssc|certificate)\b")
    for line in lines:
        clean = _BULLET.sub("", line)
        buf.append(clean)
        year = _RANGE.search(clean) or _SINGLE_YEAR.search(clean)
        if year or len(buf) >= 3:
            text = " | ".join(buf)
            ym = _RANGE.search(text)
            year_text = ym.group(0) if ym else (_SINGLE_YEAR.search(text).group(1) if _SINGLE_YEAR.search(text) else "")
            body = text.replace(year_text, "") if year_text else text
            parts = _split_header(body)
            entry: Dict[str, Any] = {}
            deg = next((p for p in parts if degree_words.search(p)), None)
            if deg:
                entry["degree"] = deg
                rest = [p for p in parts if p != deg]
                if rest:
                    entry["institution"] = rest[0]
            elif parts:
                entry["institution"] = parts[0]
                if len(parts) > 1:
                    entry["degree"] = parts[1]
            if year_text:
                entry["year"] = year_text
            if entry.get("degree") or entry.get("institution"):
                entries.append(entry)
            buf = []
    return entries


def parse_projects(lines: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for line in lines:
        clean = _BULLET.sub("", line)
        m = re.match(r"^(.{3,60}?)\s+(?:[-–—:|])\s+(.{10,})$", clean)
        if m:
            out.append({"name": m.group(1).strip(), "description": m.group(2).strip()})
        elif _is_header_line(clean) and len(clean) <= 60:
            out.append({"name": clean})
        elif out:
            out[-1]["description"] = (out[-1].get("description", "") + " " + clean).strip()
    return out[:10]


def fallback_extract(text: str) -> Dict[str, Any]:
    """Quick literal extraction (no AI, < 1 s): copies only text that is in the CV, into the right fields."""
    sections = split_sections(text)
    personal: Dict[str, str] = {}
    m = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text)
    if m:
        personal["email"] = m.group(0)
    for m in re.finditer(r"(?<![\w])(\+?\d[\d\s().-]{7,}\d)(?![\w])", text):
        cand = m.group(1).strip()
        if len(_digits(cand)) >= 8 and not _RANGE.search(cand) and not re.fullmatch(r"(?:19|20)\d{2}\s*[-–]\s*(?:19|20)\d{2}", cand):
            personal["phone"] = cand
            break
    m = re.search(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[A-Za-z0-9_-]+/?", text, re.I)
    if m:
        personal["linkedin"] = m.group(0)
    m = re.search(r"(?:https?://)?(?:www\.)?github\.com/[A-Za-z0-9_-]+/?", text, re.I)
    if m:
        personal["github"] = m.group(0)

    top = sections.get("_top") or [l.strip() for l in text.splitlines() if l.strip()][:4]
    professional: Dict[str, Any] = {}
    for idx, line in enumerate(top[:3]):
        mm = re.match(r"(?:name\s*[:\-]\s*)?([A-Za-z][a-zA-Z'.-]+(?:\s+[A-Za-z][a-zA-Z'.-]+){1,3})$", line)
        if mm and not re.search(r"\d|@|http", line):
            personal["name"] = mm.group(1)
            nxt = top[idx + 1] if idx + 1 < len(top) else ""
            if nxt and len(nxt.split()) <= 10 and not re.search(r"@|\d{3}|http", nxt):
                professional["headline"] = nxt.split(" | ")[0].strip()
            break
    for line in (top + text.splitlines())[:12]:
        if "@" in line or re.search(r"\d{3}", line):
            for seg in re.split(r"[|·•]", line):
                seg = seg.strip()
                if re.fullmatch(r"[A-Z][A-Za-z .'-]{1,30},\s*[A-Z][A-Za-z .'-]{1,30}", seg):
                    personal["location"] = seg
                    break
        if "location" in personal:
            break
    m = re.search(r"(?im)^\s*(?:location|address)\s*[:\-]\s*(.{3,60})$", text)
    if m:
        personal["location"] = m.group(1).strip()

    summary_lines = _section_lines(sections, "PROFILE", "SUMMARY", "ABOUT ME", "PROFESSIONAL SUMMARY", "EXECUTIVE SUMMARY", "OBJECTIVE")
    if summary_lines:
        professional["summary"] = re.sub(r"\s+", " ", " ".join(summary_lines))[:1200]

    found: List[str] = []
    for sk in SKILL_KEYWORDS:
        if re.search(r"(?<![\w])" + re.escape(sk) + r"(?![\w])", text, re.I):
            found.append(sk)
    for line in _section_lines(sections, "SKILLS", "TECHNICAL SKILLS", "CORE SKILLS"):
        for item in re.split(r"[,|•;·]", _BULLET.sub("", line)):
            item = item.strip(" -*:")
            if 1 < len(item) <= 40 and not re.search(r"[.!?]$", item) and len(item.split()) <= 5:
                found.append(item)
    skills = {"technical": [], "frameworks": [], "tools": []}
    for s in found:
        cat = "frameworks" if s.lower() in FRAMEWORK_WORDS else "tools" if s.lower() in TOOL_WORDS else "technical"
        skills[cat].append(s)
    skills = normalize_skills(skills)

    certs = [_BULLET.sub("", l) for l in _section_lines(sections, "CERTIFICATIONS", "CERTIFICATES", "LICENSES") if len(l) > 3]
    experience = parse_experience(_section_lines(sections, "EXPERIENCE", "WORK EXPERIENCE", "EMPLOYMENT HISTORY", "PROFESSIONAL EXPERIENCE"))
    for e in experience:
        y = _years_between(e.get("start_date", ""), e.get("end_date", ""))
        if y is not None:
            e["years"] = y
    education = parse_education(_section_lines(sections, "EDUCATION", "ACADEMIC BACKGROUND"))
    projects = parse_projects(_section_lines(sections, "PROJECTS", "KEY PROJECTS"))

    flat = flatten_skills(skills)
    if flat:
        professional["skills"] = flat
    stated = _stated_years(text)
    if stated is not None:
        professional["experience_years"] = stated
    elif experience:
        total = sum(e.get("years", 0) for e in experience)
        if total:
            professional["experience_years"] = total
    return {"personal": personal, "professional": professional, "skills": skills if flat else {},
            "experience": experience, "education": education, "projects": projects, "certifications": certs}


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


def _merge_missing(primary: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    """Fill gaps in the AI result with values the quick literal read found (both come from the CV)."""
    out = dict(primary)
    for section in ("personal", "professional"):
        merged = dict(extra.get(section) or {})
        merged.update({k: v for k, v in (primary.get(section) or {}).items() if v not in (None, "", [], {})})
        out[section] = merged
    for section in ("experience", "education", "projects", "certifications"):
        if not primary.get(section) and extra.get(section):
            out[section] = extra[section]
    if not flatten_skills(primary.get("skills") or {}) and flatten_skills(extra.get("skills") or {}):
        out["skills"] = extra["skills"]
    return out


class ProfileAgent:
    def _package(self, profile: Dict[str, Any], method: str, dropped: List[str], message: str) -> Dict[str, Any]:
        missing = missing_fields(profile)
        source = {"llm": "cv_ai_extraction", "quick": "cv_quick_read"}.get(method, "cv_literal_fallback")
        return {
            "facts": build_facts(profile, source, 0.9 if method == "llm" else 0.7),
            "profile_data": profile,
            "missing_fields": missing,
            "followup_questions": [QUESTIONS[m] for m in missing if m in QUESTIONS],
            "extraction_method": method,
            "dropped": dropped,
            "message": message,
        }

    def quick_extract(self, text: str) -> Dict[str, Any]:
        """Instant literal read (no AI): fills the fields with text copied from the CV."""
        if not text or not text.strip():
            return self.extract_from_text(text)
        profile = fallback_extract(text[:MAX_INPUT_CHARS])
        run_log("info", "Quick read: fields filled with text copied from the CV (AI refinement follows)")
        return self._package(profile, "quick", [], "")

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
                                   system_prompt=SYSTEM_PROMPT, temperature=0.0, max_tokens=MAX_TOKENS,
                                   timeout=extraction_timeout())
            if not isinstance(raw, dict):
                raise ValueError("model did not return a JSON object")
            profile, dropped = ground_profile(raw, source_text)
            profile = _merge_missing(profile, fallback_extract(source_text))
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

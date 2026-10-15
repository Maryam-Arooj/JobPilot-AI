"""Grounded CV tailoring: the LLM may only rephrase and reorder what the CV already says.

Everything the model returns is validated here before it reaches the user; anything that
introduces an employer, skill, certification, number or missing keyword is dropped.
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional

from .nvidia_llm import call_nvidia_llm

logger = logging.getLogger(__name__)

LLM_TIMEOUT_SECONDS = 45
MAX_GAPS = 15
MAX_NOTES = 8

SYSTEM_PROMPT = """You tailor an existing CV to a target role. You are an editor, not an author.

HARD RULES — breaking any of them makes the output unusable:
- Use ONLY facts in the provided CV and VERIFIED PROFILE FACTS.
- NEVER invent or add employers, job titles, dates, degrees, institutions, certifications,
  metrics, numbers, percentages, tools or skills.
- Do not add new experience entries and do not add bullets; you may only rephrase the existing
  bullets of an existing entry, keeping the same meaning, to emphasise work relevant to the role.
- Skills: return the CV's own skills reordered by relevance. Do not add, rename or remove any.
- Keywords from the job description that the CV does not support go ONLY into "gaps".
  Never mention a gap keyword in the summary or bullets.
- If the CV has nothing relevant to say, keep the original wording.

Respond with ONE JSON object and nothing else:
{
  "title": "CV headline for the target role, built from the target role and the CV",
  "summary": "rewritten professional summary (2-4 sentences)",
  "skills_order": ["existing skill", "..."],
  "experience": [{"index": 0, "bullets": ["rephrased existing bullet", "..."]}],
  "gaps": ["keyword from the job description missing from the CV"],
  "notes": ["short explanation of what you changed and why"]
}"""

# Digits only, so "40%" / "40 percent" and "1,000" / "1000" count as the same fact.
NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
# Proper nouns introduced as an employer/tool, e.g. "at Google", "with Kubernetes", "@ Meta".
NAMED_RE = re.compile(r"(?:\b(?:at|for|with|joined)\s+|@\s*)([A-Z][\w&.+#-]*(?:\s+[A-Z][\w&.+#-]*)*)")
CERT_RE = re.compile(r"\bcertif\w*|\blicen[cs]\w*", re.I)


class TailorUnavailable(Exception):
    """LLM could not be reached or returned nothing usable."""


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _numbers(text: str) -> set:
    return {m.replace(",", "") for m in NUMBER_RE.findall(text or "")}


def _mentions(text: str, term: str) -> bool:
    term = _norm(term)
    if not term:
        return False
    return re.search(r"(?<![\w+#])" + re.escape(term) + r"(?![\w+#])", _norm(text)) is not None


def _parse_json(raw: str) -> Dict[str, Any]:
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in LLM output")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("LLM output is not a JSON object")
    return data


def build_prompt(target_role: str, cv: Dict[str, Any], job_description: str, facts: List[Dict[str, str]]) -> str:
    indexed_exp = [
        {"index": i, "role": e.get("role", ""), "company": e.get("company", ""),
         "period": e.get("period", ""), "bullets": e.get("bullets", [])}
        for i, e in enumerate(cv.get("experience", []))
    ]
    payload = {
        "target_role": target_role,
        "cv": {
            "title": cv.get("title", ""),
            "summary": cv.get("summary", ""),
            "experience": indexed_exp,
            "skills": cv.get("skills", []),
            "education": cv.get("education", []),
            "certifications": cv.get("certifications", []),
        },
        "verified_profile_facts": facts,
        "job_description": (job_description or "")[:6000],
    }
    return "Tailor this CV. Input JSON:\n" + json.dumps(payload, ensure_ascii=False)


def validate(result: Dict[str, Any], target_role: str, cv: Dict[str, Any], facts: List[Dict[str, str]]) -> Dict[str, Any]:
    """Keep only grounded changes. Returns the API response shape."""
    notes: List[str] = []
    source_text = json.dumps({"cv": cv, "facts": facts}, ensure_ascii=False)
    allowed_numbers = _numbers(source_text)
    cv_skills = [str(s) for s in cv.get("skills", []) if str(s).strip()]
    skill_by_norm = {_norm(s): s for s in cv_skills}
    experience = cv.get("experience", [])

    # Gaps first: rewrites that claim a gap keyword are rejected below.
    gaps: List[str] = []
    for g in result.get("gaps") or []:
        if not isinstance(g, str) or not g.strip():
            continue
        g = g.strip()[:60]
        if _norm(g) in skill_by_norm or any(_norm(g) == _norm(x) for x in gaps):
            continue
        if _mentions(source_text, g):
            continue  # the CV already covers it, so it isn't a gap
        gaps.append(g)
    gaps = gaps[:MAX_GAPS]

    cv_certs = [str(c.get("name") or c.get("title") or "") if isinstance(c, dict) else str(c)
                for c in cv.get("certifications", [])]

    def grounded(text: str, original: str) -> Optional[str]:
        """Reason the rewrite is ungrounded, or None if it is acceptable."""
        new_numbers = _numbers(text) - allowed_numbers - _numbers(original)
        if new_numbers:
            return f"introduced numbers not in your CV ({', '.join(sorted(new_numbers))})"
        claimed = [g for g in gaps if _mentions(text, g) and not _mentions(original, g)]
        if claimed:
            return f"claimed skills your CV doesn't show ({', '.join(claimed)})"
        named = [n for n in NAMED_RE.findall(text) if not _mentions(source_text + " " + original, n)]
        if named:
            return f"named an employer or tool not in your CV ({', '.join(named[:3])})"
        if CERT_RE.search(text) and not CERT_RE.search(original) and not any(_mentions(text, c) for c in cv_certs if c):
            return "mentioned a certification not in your CV"
        return None

    # Title
    title = result.get("title")
    title = title.strip()[:120] if isinstance(title, str) and title.strip() else target_role
    reason = grounded(title, cv.get("title", "") + " " + target_role)
    if reason:
        notes.append(f"Kept a plain title: the suggested one {reason}.")
        title = target_role

    # Summary
    original_summary = cv.get("summary", "") or ""
    summary = result.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        summary = original_summary
    else:
        summary = summary.strip()
        reason = grounded(summary, original_summary)
        if reason:
            notes.append(f"Rejected the rewritten summary: it {reason}.")
            summary = original_summary

    # Skills: reorder only; never add, drop or rename.
    order: List[str] = []
    dropped_skills: List[str] = []
    for s in result.get("skills_order") or []:
        key = _norm(s)
        if key in skill_by_norm:
            if skill_by_norm[key] not in order:
                order.append(skill_by_norm[key])
        elif isinstance(s, str) and s.strip():
            dropped_skills.append(s.strip())
    order += [s for s in cv_skills if s not in order]
    if dropped_skills:
        notes.append(f"Removed skills not in your CV: {', '.join(dropped_skills[:10])}.")

    # Experience: rephrase bullets of existing entries only.
    exp_out: List[Dict[str, Any]] = []
    seen = set()
    for item in result.get("experience") or []:
        if not isinstance(item, dict):
            continue
        idx = item.get("index")
        if not isinstance(idx, int) or isinstance(idx, bool) or not 0 <= idx < len(experience):
            notes.append("Dropped a suggested experience entry that is not in your CV.")
            continue
        original = experience[idx]
        company = item.get("company") or item.get("employer")
        if company and _norm(company) != _norm(original.get("company")):
            notes.append(f"Dropped changes that named an employer not in your CV ({str(company)[:60]}).")
            continue
        if idx in seen:
            notes.append(f"Ignored a duplicate suggestion for entry {idx + 1}.")
            continue
        role = item.get("role") or item.get("title")
        if role and _norm(role) != _norm(original.get("role")):
            notes.append(f"Ignored a changed job title for entry {idx + 1}; titles are never rewritten.")
        orig_bullets = [str(b) for b in original.get("bullets", [])]
        new_bullets = [b.strip() for b in (item.get("bullets") or []) if isinstance(b, str) and b.strip()]
        if not orig_bullets or not new_bullets:
            continue
        if len(new_bullets) > len(orig_bullets):
            notes.append(f"Ignored extra bullets suggested for entry {idx + 1}; only existing bullets are rephrased.")
        bullets = []
        for i, orig in enumerate(orig_bullets):
            candidate = new_bullets[i] if i < len(new_bullets) and orig.strip() else orig
            reason = grounded(candidate, orig)
            if reason:
                notes.append(f"Kept your original bullet {i + 1} of entry {idx + 1}: the rewrite {reason}.")
                candidate = orig
            bullets.append(candidate)
        seen.add(idx)
        if bullets != orig_bullets:
            exp_out.append({"index": idx, "bullets": bullets})

    if result.get("certifications"):
        notes.append("Ignored suggested certifications; tailoring never changes certifications.")

    for n in result.get("notes") or []:
        if isinstance(n, str) and n.strip() and len(notes) < MAX_NOTES:
            notes.append(n.strip()[:300])

    return {
        "title": title,
        "summary": summary,
        "skills_order": order,
        "experience": exp_out,
        "gaps": gaps,
        "notes": notes[:MAX_NOTES],
    }


def tailor_cv(target_role: str, cv: Dict[str, Any], job_description: str, facts: List[Dict[str, str]]) -> Dict[str, Any]:
    prompt = build_prompt(target_role, cv, job_description, facts)
    try:
        raw = call_nvidia_llm(prompt, system_prompt=SYSTEM_PROMPT, temperature=0.2,
                              max_tokens=2000, timeout=LLM_TIMEOUT_SECONDS)
    except Exception as e:
        logger.error("Resume tailoring LLM call failed: %s", e)
        raise TailorUnavailable("unreachable") from e
    if not raw or not raw.strip():
        raise TailorUnavailable("unreachable")
    try:
        parsed = _parse_json(raw)
    except (ValueError, json.JSONDecodeError) as e:
        logger.error("Resume tailoring LLM returned invalid JSON: %s; head=%r", e, raw[:200])
        raise TailorUnavailable("invalid") from e
    return validate(parsed, target_role, cv, facts)

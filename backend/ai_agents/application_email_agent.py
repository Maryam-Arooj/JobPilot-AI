"""Email Agent: writes an application email from REAL facts only.

Facts come from three places: the user's CV/profile, the job posting, and company research read from the
company's own website. The AI writes the email; then a checker removes any sentence that
  * contains a number (years, %, counts) that is in none of the sources, or
  * claims a skill/tool in the first person ("I", "my") that is not in the user's CV, or
  * says something about the company that is not supported by the research.
If the AI is unavailable, an honest template is used (no "verified expertise", no default industry).
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from ..services.agent_runs import run_log, run_warn
from ..services.job_matching import VOCAB, _mentions, candidate_skills, candidate_title

TONE_GUIDE = {
    "Formal": "formal and polite, like a classic cover email",
    "Technical": "technical: name the concrete tools and projects from the CV that match the job",
    "Concise": "very short (under 90 words), direct, no filler",
    "Networking": "warm and conversational, asking for a short chat",
    "Cold Outreach": "a short cold email to a hiring manager, curious and specific",
}
NUM = re.compile(r"\d+(?:[.,]\d+)?\s*%?|\b(?:one|two|three|four|five|six|seven|eight|nine|ten)\+?\s+(?:years?|months?)\b", re.I)
FIRST_PERSON = re.compile(r"\b(i|i'm|i've|my|me)\b", re.I)


def _flat(*parts: Any) -> str:
    out: List[str] = []

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)
        elif x not in (None, ""):
            out.append(str(x))
    for p in parts:
        walk(p)
    return "\n".join(out)


def _sentences(text: str) -> List[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def _norm_num(s: str) -> str:
    return re.sub(r"[\s,%+]", "", s.lower())


class ApplicationEmailAgent:
    VALID_TONES = list(TONE_GUIDE)

    # ---------------- facts ----------------
    @staticmethod
    def facts(career_profile: Dict[str, Any], job: Dict[str, Any], company_research: Dict[str, Any]) -> Dict[str, Any]:
        personal = career_profile.get("personal") or {}
        skills = candidate_skills(career_profile)
        jtext = _flat(job.get("title"), job.get("description"), job.get("requirements"), job.get("technologies"))
        matched = [s for s in skills if _mentions(jtext, s)]
        exp = [{k: e.get(k) for k in ("title", "company", "start_date", "end_date", "description") if e.get(k)}
               for e in (career_profile.get("experience") or []) if isinstance(e, dict)][:4]
        projects = [{k: p.get(k) for k in ("name", "title", "description", "technologies") if p.get(k)}
                    for p in (career_profile.get("projects") or []) if isinstance(p, dict)][:3]
        education = [{k: e.get(k) for k in ("degree", "institution", "field", "end_date") if e.get(k)}
                     for e in (career_profile.get("education") or []) if isinstance(e, dict)][:2]
        research_ok = company_research.get("status", "found" if company_research.get("claims") else "") == "found"
        company = {k: company_research.get(k) for k in ("overview", "products_services", "technology_info", "mission_info")
                   if research_ok and company_research.get(k)}
        return {
            "name": personal.get("name") or personal.get("full_name") or "",
            "email": personal.get("email") or "",
            "phone": personal.get("phone") or "",
            "current_title": candidate_title(career_profile),
            "summary": (career_profile.get("professional") or {}).get("summary") or "",
            "skills": skills, "matched_skills": matched, "experience": exp, "projects": projects, "education": education,
            "job": {"title": job.get("title") or "", "company": job.get("company") or company_research.get("company_name") or "",
                    "location": job.get("location") or "", "description": (job.get("description") or "")[:2500]},
            "company": company,
        }

    # ---------------- checker ----------------
    @staticmethod
    def check(body: str, f: Dict[str, Any]) -> Tuple[str, List[str]]:
        cv_text = _flat(f["name"], f["current_title"], f["summary"], f["skills"], f["experience"], f["projects"], f["education"])
        job_text = _flat(f["job"])
        company_text = _flat(f["company"])
        all_text = "\n".join([cv_text, job_text, company_text])
        known_nums = {_norm_num(n) for n in NUM.findall(all_text)}
        cv_skills_l = {s.lower() for s in f["skills"]}
        kept, removed = [], []
        for line in body.split("\n"):
            out_parts = []
            for s in _sentences(line) or [line]:
                reason = None
                for n in NUM.findall(s):
                    if _norm_num(n) not in known_nums:
                        reason = f"number '{n.strip()}' is not in your CV, the job or the company research"
                        break
                if not reason and FIRST_PERSON.search(s):
                    for term in VOCAB:
                        if len(term) > 2 and term.lower() not in cv_skills_l and _mentions(s, term) and not _mentions(cv_text, term):
                            reason = f"claims '{term}', which is not in your CV"
                            break
                if not reason and not f["company"] and re.search(r"\b(your|their)\s+(mission|products?|platform|vision|values|culture|recent)\b", s, re.I):
                    reason = "talks about the company, but no company facts were found on its website"
                if reason:
                    removed.append(f"{s.strip()} — {reason}")
                else:
                    out_parts.append(s.strip() if line.strip() else s)
            kept.append(" ".join(out_parts) if line.strip() else "")
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
        return text, removed

    # ---------------- writers ----------------
    def _ai_write(self, f: Dict[str, Any], tone: str) -> Optional[Dict[str, str]]:
        from ..services.nvidia_llm import LLMError, call_nvidia_json
        import json
        system = (
            "You write a job application email for the candidate. Use ONLY the facts in the JSON. Never invent "
            "experience, years, numbers, achievements, degrees, skills or company facts. If company facts are empty, "
            "do not describe the company beyond its name and the role. Mention 2-4 of the matched skills and one real "
            "project or job from the CV if present. Say the CV is attached. 120-180 words unless the tone says shorter. "
            f"Tone: {TONE_GUIDE[tone]}. Do not include the greeting line or the sign-off. Return JSON: "
            '{"subject": str, "body": str}')
        try:
            data = call_nvidia_json(json.dumps(f, ensure_ascii=False), system_prompt=system,
                                    temperature=0.4, max_tokens=900, timeout=45)
        except LLMError as e:
            run_warn(f"AI email writer unavailable ({e}); an honest template is used instead.")
            return None
        if not isinstance(data, dict) or not str(data.get("body") or "").strip():
            run_warn("AI email writer returned no body; an honest template is used instead.")
            return None
        return {"subject": str(data.get("subject") or "").strip()[:150], "body": str(data["body"]).strip()}

    @staticmethod
    def _template(f: Dict[str, Any], tone: str) -> Dict[str, str]:
        role, company = f["job"]["title"] or "the open role", f["job"]["company"] or "your company"
        skills = f["matched_skills"][:4] or f["skills"][:3]
        exp = f["experience"][0] if f["experience"] else None
        proj = f["projects"][0] if f["projects"] else None
        lines = [f"I am applying for the {role} position at {company}."]
        if exp and exp.get("title"):
            lines.append(f"My most recent role is {exp['title']}" + (f" at {exp['company']}." if exp.get("company") else "."))
        if skills:
            lines.append(f"The role asks for skills I have used in my work, including {', '.join(skills)}.")
        if proj and (proj.get("name") or proj.get("title")):
            lines.append(f"One relevant project from my CV is {proj.get('name') or proj.get('title')}.")
        if f["company"].get("overview") and tone != "Concise":
            lines.append(f"From your website I learned that {f['company']['overview'][0].lower() + f['company']['overview'][1:]}")
        lines.append("My CV is attached, and I would welcome the chance to talk about the role.")
        subject = {"Concise": f"{role} - {f['name']}", "Networking": f"Quick chat about the {role} role at {company}",
                   "Cold Outreach": f"{f['name']} - interested in {role} at {company}"}.get(tone, f"Application for {role} - {f['name']}")
        return {"subject": subject.strip(" -"), "body": " ".join(lines) if tone == "Concise" else "\n\n".join([" ".join(lines[:2]), " ".join(lines[2:])]).strip()}

    def generate_email(self, career_profile: Dict[str, Any], job: Dict[str, Any], job_analysis: Dict[str, Any] = None,
                       job_match: Dict[str, Any] = None, company_research: Dict[str, Any] = None,
                       resume_version: Dict[str, Any] = None, tone: str = "Formal", use_ai: bool = True) -> Dict[str, Any]:
        tone = tone if tone in TONE_GUIDE else "Formal"
        f = self.facts(career_profile or {}, job or {}, company_research or {})
        written = self._ai_write(f, tone) if use_ai else None
        method = "ai" if written else "template"
        if not written:
            written = self._template(f, tone)
        body, removed = self.check(written["body"], f)
        subject, removed_subj = self.check(written["subject"] or "", f)
        removed += removed_subj
        if not subject:
            subject = f"Application for {f['job']['title']} - {f['name']}".strip(" -")
        if removed:
            run_log("warn", f"Email checker removed {len(removed)} unsupported sentence(s)")
        if len(body) < 60:  # the checker removed too much: fall back to the template, which is checked too
            body, more = self.check(self._template(f, tone)["body"], f)
            removed += more
            method = "template"
        company = f["job"]["company"]
        greeting = {"Concise": f"Hi {company} team,", "Networking": f"Hello {company} team,",
                    "Cold Outreach": "Hi,"}.get(tone, f"Dear {company} Hiring Team," if company else "Dear Hiring Team,")
        closing = "\n".join(x for x in ["Best regards," if tone != "Formal" else "Sincerely,", f["name"], f["email"], f["phone"]] if x)
        return {
            "subject": subject, "greeting": greeting, "closing": closing, "tone": tone, "method": method,
            "body": f"{greeting}\n\n{body}\n\n{closing}",
            "removed_claims": removed,
            "referenced_profile_facts": ([f"name: {f['name']}"] if f["name"] else []) + [f"skill: {s}" for s in f["matched_skills"][:4]],
            "referenced_job_requirements": [f"role: {f['job']['title']}"] + [f"requires: {s}" for s in f["matched_skills"][:4]],
            "referenced_company_claims": [f"{k}: {v if isinstance(v, str) else ', '.join(v)}" for k, v in f["company"].items()],
        }

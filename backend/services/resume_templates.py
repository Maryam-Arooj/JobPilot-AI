from abc import ABC, abstractmethod
from typing import Dict, Any

class ResumeTemplate(ABC):
    name: str

    @abstractmethod
    def get_default_sections(self) -> list:
        pass

    @abstractmethod
    def render_html(self, doc: Dict[str, Any]) -> str:
        pass

    @abstractmethod
    def get_section_order(self) -> list:
        pass

def format_section_html(sec: str, items: Any) -> str:
    if sec in ["certifications", "skills", "technical_skills", "achievements", "publications"] and isinstance(items, list):
        lis = []
        for it in items:
            if isinstance(it, dict):
                n = it.get("name") or it.get("title") or ""
                iss = it.get("issuer") or it.get("authority") or ""
                dt = it.get("date") or it.get("year") or ""
                p = [x for x in [n, iss, str(dt)] if x]
                lis.append(f"<li>{' — '.join(p) if p else str(it)}</li>")
            else:
                lis.append(f"<li>{it}</li>")
        return f"<ul>{''.join(lis)}</ul>"
    return f"<div>{items}</div>"

class ATSTemplate(ResumeTemplate):
    name = "ATS"
    def get_default_sections(self):
        return ["header","professional_summary","experience","education","skills","projects","certifications","achievements","publications","links"]
    def get_section_order(self):
        return self.get_default_sections()
    def render_html(self, doc):
        # Simple ATS safe HTML
        parts = []
        parts.append(f"<h1>{doc['header'].get('name','')}</h1>")
        if doc.get('professional_summary'):
            parts.append(f"<h2>Professional Summary</h2><p>{doc['professional_summary']}</p>")
        for sec in self.get_section_order():
            if sec in ["header","professional_summary"]: continue
            items = doc.get(sec, [])
            if not items: continue
            parts.append(f"<h2>{sec.replace('_',' ').title()}</h2>")
            parts.append(format_section_html(sec, items))
        return "\n".join(parts)

class ModernProfessionalTemplate(ResumeTemplate):
    name = "Modern Professional"
    def get_default_sections(self):
        return ["header","professional_summary","experience","education","skills","projects","certifications","achievements"]
    def get_section_order(self):
        return self.get_default_sections()
    def render_html(self, doc):
        parts = []
        parts.append(f"<div class='header'><h1>{doc['header'].get('name','')}</h1></div>")
        if doc.get('professional_summary'):
            parts.append(f"<section><h2>Summary</h2><p>{doc['professional_summary']}</p></section>")
        for sec in self.get_section_order():
            if sec in ["header","professional_summary"]: continue
            items = doc.get(sec, [])
            if not items: continue
            parts.append(f"<section><h2>{sec.replace('_',' ').title()}</h2>{format_section_html(sec, items)}</section>")
        return "\n".join(parts)

class TechnicalResumeTemplate(ResumeTemplate):
    name = "Technical"
    def get_default_sections(self):
        return ["header","professional_summary","technical_skills","experience","projects","education","certifications","links"]
    def get_section_order(self):
        return self.get_default_sections()
    def render_html(self, doc):
        parts = []
        parts.append(f"<h1>{doc['header'].get('name','')}</h1>")
        if doc.get('professional_summary'):
            parts.append(f"<h2>Summary</h2><p>{doc['professional_summary']}</p>")
        # Map skills to technical_skills
        doc_section = dict(doc)
        if doc_section.get('skills') and not doc_section.get('technical_skills'):
            doc_section['technical_skills'] = doc_section['skills']
        for sec in self.get_section_order():
            if sec in ["header","professional_summary"]: continue
            items = doc_section.get(sec, [])
            if not items: continue
            parts.append(f"<h2>{sec.replace('_',' ').title()}</h2>{format_section_html(sec, items)}")
        return "\n".join(parts)

TEMPLATES = {
    "ATS": ATSTemplate(),
    "Modern Professional": ModernProfessionalTemplate(),
    "Technical": TechnicalResumeTemplate(),
}

def get_template(name: str) -> ResumeTemplate:
    return TEMPLATES.get(name)

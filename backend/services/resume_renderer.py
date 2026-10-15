from ..services.resume_templates import get_template
from typing import Dict, Any

class ResumeRenderer:
    def __init__(self, template_name: str):
        self.template = get_template(template_name)

    def render_preview(self, doc: Dict[str, Any]) -> str:
        if not self.template:
            return "<p>Template not found</p>"
        return self.template.render_html(doc)

    def render_for_export(self, doc: Dict[str, Any]) -> str:
        # Same rendering pipeline as preview
        return self.render_preview(doc)

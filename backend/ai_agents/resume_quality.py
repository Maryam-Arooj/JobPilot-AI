from typing import Dict, Any, List

class ResumeQualityAgent:
    def check(self, doc: Dict[str, Any], career_profile: Dict[str, Any], template: str) -> Dict[str, Any]:
        issues = []
        warnings = []
        suggestions = []
        
        # Fact check
        header_name = doc.get("header", {}).get("name", "")
        profile_name = career_profile.get("personal", {}).get("name", "")
        if header_name and profile_name and header_name != profile_name:
            issues.append("Name mismatch between resume and career profile")
        
        # Grammar / empty sections
        summary = doc.get("professional_summary", "")
        if not summary:
            warnings.append("Professional summary is empty")
        else:
            suggestions.append("Review summary for clarity")
        
        # ATS check
        if template == "ATS":
            sections = doc.get("sections_order", [])
            required = ["experience","education","skills"]
            for r in required:
                if r not in sections:
                    issues.append(f"ATS template missing section {r}")
        
        # Formatting check
        if not doc.get("experience"):
            warnings.append("Experience section empty")
        if not doc.get("education"):
            warnings.append("Education section empty")
        
        status = "pass" if not issues else "fail"
        return {
            "status": status,
            "issues": issues,
            "warnings": warnings,
            "suggestions": suggestions
        }

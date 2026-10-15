from typing import Dict

def calculate_completeness(profile_data: Dict) -> int:
    sections = {
        "personal": ["name", "email", "location", "country"],
        "professional": ["headline", "summary"],
        "education": [],
        "experience": [],
        "skills": ["technical", "soft"],
    }
    total = 0
    filled = 0
    for sec, fields in sections.items():
        data = profile_data.get(sec) or {}
        if not fields:
            if data:
                total += 1
                filled += 1
            continue
        for f in fields:
            total += 1
            if data.get(f):
                filled += 1
    if total == 0:
        return 0
    return int((filled / total) * 100)

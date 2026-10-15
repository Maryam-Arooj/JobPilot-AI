from typing import Dict, Any, List

class JobMatchAgent:
    def match(self, career_profile: Dict[str, Any], job: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
        profile_skills = set()
        skills_data = career_profile.get("skills", {})
        if isinstance(skills_data, dict):
            for v in skills_data.values():
                if isinstance(v, list):
                    profile_skills.update([str(s).lower().strip() for s in v])
                elif isinstance(v, str):
                    profile_skills.add(v.lower().strip())
        elif isinstance(skills_data, list):
            profile_skills.update([str(s).lower().strip() for s in skills_data])

        # Extract required & preferred skills
        req_skills = [str(s).lower().strip() for s in analysis.get("required_skills", [])]
        pref_skills = [str(s).lower().strip() for s in analysis.get("preferred_skills", [])]

        matched_req = [s for s in req_skills if any(p in s or s in p for p in profile_skills)]
        gaps_req = [s for s in req_skills if not any(p in s or s in p for p in profile_skills)]
        matched_pref = [s for s in pref_skills if any(p in s or s in p for p in profile_skills)]

        evidence = []
        # Skill evidence
        for s in matched_req:
            matching_fact = next((p for p in profile_skills if p in s or s in p), s)
            evidence.append({
                "type": "skill_match",
                "career_profile_fact_path": "skills",
                "job_requirement_text": f"Required skill: {s}",
                "explanation": f"Matched because '{matching_fact}' is present in confirmed technical skills in Canonical Career Profile."
            })
        for s in matched_pref:
            matching_fact = next((p for p in profile_skills if p in s or s in p), s)
            evidence.append({
                "type": "preferred_skill_match",
                "career_profile_fact_path": "skills",
                "job_requirement_text": f"Preferred skill: {s}",
                "explanation": f"Preferred skill '{matching_fact}' matched from verified technical skills."
            })

        # Experience matching
        exp_list = career_profile.get("experience") or []
        verified_exp_years = 0
        for exp in exp_list:
            if isinstance(exp, dict) and exp.get("years"):
                try:
                    verified_exp_years += float(exp.get("years", 0))
                except ValueError:
                    pass
        
        req_exp_years = analysis.get("experience_requirements") or job.get("experience_years") or 0
        exp_matched = verified_exp_years >= req_exp_years if req_exp_years else True

        if req_exp_years > 0:
            if exp_matched:
                evidence.append({
                    "type": "experience_match",
                    "career_profile_fact_path": "experience",
                    "job_requirement_text": f"{req_exp_years} years experience required",
                    "explanation": f"Requirement of {req_exp_years} years matched with verified profile experience (~{verified_exp_years} years)."
                })
            else:
                gaps_req.append(f"{req_exp_years} years experience required ({verified_exp_years} years verified)")

        # Overall Alignment calculation
        total_reqs = len(req_skills) + (1 if req_exp_years > 0 else 0)
        matched_count = len(matched_req) + (1 if req_exp_years > 0 and exp_matched else 0)

        if total_reqs == 0:
            overall = "Strong Alignment"
        else:
            match_pct = (matched_count / total_reqs) * 100
            if match_pct >= 75:
                overall = "Strong Alignment"
            elif match_pct >= 40:
                overall = "Review"
            else:
                overall = "Limited Alignment"

        return {
            "overall_alignment": overall,
            "skills_match": {
                "matched": matched_req,
                "preferred_matched": matched_pref,
                "gaps": gaps_req
            },
            "experience_match": {
                "required_years": req_exp_years,
                "verified_years": verified_exp_years,
                "matched": exp_matched
            },
            "education_match": {
                "matched": True
            },
            "location_match": {
                "job_location": job.get("location"),
                "remote": job.get("remote")
            },
            "responsibility_match": {},
            "matched_requirements": matched_req,
            "gaps": gaps_req,
            "evidence": evidence
        }


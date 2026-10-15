from typing import Dict, Any, List

class ApplicationEmailAgent:
    VALID_TONES = ["Formal", "Technical", "Concise", "Networking", "Cold Outreach"]

    def generate_email(
        self,
        career_profile: Dict[str, Any],
        job: Dict[str, Any],
        job_analysis: Dict[str, Any],
        job_match: Dict[str, Any],
        company_research: Dict[str, Any],
        resume_version: Dict[str, Any],
        tone: str = "Formal"
    ) -> Dict[str, Any]:
        if tone not in self.VALID_TONES:
            tone = "Formal"

        # Extract verified facts from canonical profile
        personal = career_profile.get("personal", {})
        user_name = personal.get("name") or personal.get("full_name") or "Applicant"
        user_email = personal.get("email", "")

        skills_dict = career_profile.get("skills", {})
        verified_skills = []
        if isinstance(skills_dict, dict):
            for v in skills_dict.values():
                if isinstance(v, list):
                    verified_skills.extend([str(s) for s in v])
                elif isinstance(v, str):
                    verified_skills.append(v)
        elif isinstance(skills_dict, list):
            verified_skills.extend([str(s) for s in skills_dict])

        job_title = job.get("title", "Target Role")
        company_name = job.get("company") or company_research.get("company_name", "the company")

        # Matched skills citations
        matched_reqs = job_match.get("matched_requirements", [])
        highlight_skills = [s for s in matched_reqs if any(s.lower() in vs.lower() for vs in verified_skills)]
        if not highlight_skills and verified_skills:
            highlight_skills = verified_skills[:3]

        ref_profile_facts = [
            f"personal.name: {user_name}",
            f"skills: {', '.join(highlight_skills[:4])}"
        ]

        ref_job_reqs = [f"role: {job_title}"] + [f"requirement: {r}" for r in matched_reqs[:3]]
        
        tech_claims = company_research.get("technology_info", [])
        ref_company_claims = [f"company: {company_name}"] + [f"tech_stack: {t}" for t in tech_claims[:2]]

        # Generate grounded email copy based on tone variant
        greeting = f"Dear Hiring Team at {company_name},"
        
        if tone == "Technical":
            subject = f"Application for {job_title} - {user_name} (Technical Background in {', '.join(highlight_skills[:2])})"
            body = (
                f"I am writing to express my strong interest in the {job_title} position at {company_name}.\n\n"
                f"My background aligns directly with your engineering requirements. I have hands-on experience building systems with "
                f"{', '.join(highlight_skills[:4]) if highlight_skills else 'modern software engineering tools'}.\n\n"
                f"I admire {company_name}'s work in {company_research.get('industry', 'the technology sector')}, particularly your focus on scalable architectures. "
                f"I have attached my tailored resume for your review and look forward to discussing how my verified skills can contribute to your engineering goals."
            )
        elif tone == "Concise":
            subject = f"{job_title} Role - {user_name}"
            greeting = f"Hi {company_name} Recruiting Team,"
            body = (
                f"I am applying for the {job_title} role at {company_name}.\n\n"
                f"Key verified qualifications:\n"
                f"• Technical Stack: {', '.join(highlight_skills[:3]) if highlight_skills else 'Software Engineering'}\n"
                f"• Verified Alignment: Direct match with your core requirements.\n\n"
                f"My complete resume is attached. I would welcome the opportunity for a brief conversation."
            )
        elif tone == "Networking":
            subject = f"Connecting regarding {job_title} opportunity at {company_name}"
            greeting = f"Hello {company_name} Team,"
            body = (
                f"I have been following {company_name}'s recent work in {company_research.get('industry', 'tech')} with great interest, "
                f"especially your developments in {', '.join(tech_claims[:2]) if tech_claims else 'engineering'}.\n\n"
                f"I am reaching out regarding the {job_title} opening. My background includes confirmed experience in "
                f"{', '.join(highlight_skills[:3]) if highlight_skills else 'software development'}. "
                f"I would love to connect and share how my experience aligns with your team's mission.\n\n"
                f"I have attached my resume for your reference."
            )
        elif tone == "Cold Outreach":
            subject = f"Introducing {user_name} - Potential fit for {job_title} at {company_name}"
            greeting = f"Hi {company_name} Engineering Lead,"
            body = (
                f"I noticed {company_name} is actively expanding its team for the {job_title} position.\n\n"
                f"With verified expertise in {', '.join(highlight_skills[:3]) if highlight_skills else 'relevant technical tools'}, "
                f"I have solved similar technical challenges and am eager to bring this capability to {company_name}.\n\n"
                f"Please find my attached resume. I would appreciate 10 minutes to discuss how I can add immediate value to your projects."
            )
        else: # Formal
            subject = f"Application for {job_title} Position - {user_name}"
            body = (
                f"Please accept this application for the {job_title} role currently open at {company_name}.\n\n"
                f"Having reviewed your requirements, I am confident that my confirmed experience in "
                f"{', '.join(highlight_skills[:4]) if highlight_skills else 'technical development'} prepares me to contribute effectively to your team. "
                f"Furthermore, {company_name}'s commitment to {company_research.get('industry', 'excellence')} makes this opportunity particularly exciting.\n\n"
                f"Thank you for considering my application. My complete resume is attached for your review."
            )

        closing = f"Sincerely,\n{user_name}\n{user_email}".strip()
        full_body = f"{greeting}\n\n{body}\n\n{closing}"

        return {
            "subject": subject,
            "greeting": greeting,
            "body": full_body,
            "closing": closing,
            "tone": tone,
            "referenced_profile_facts": ref_profile_facts,
            "referenced_job_requirements": ref_job_reqs,
            "referenced_company_claims": ref_company_claims
        }

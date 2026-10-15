import pytest
from fastapi.testclient import TestClient
from backend.api.main import app
from backend.services.auth_service import create_token
from backend.db.database import SessionLocal
from backend.models.career_profile import User, CareerProfile
from backend.models.jobs import Job
from backend.models.companies import Company

client = TestClient(app)

def setup_phase4_fixtures():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "phase4user@example.com").first()
        if not user:
            user = User(email="phase4user@example.com", password_hash="passhash")
            db.add(user)
            db.commit()
            db.refresh(user)

        profile = db.query(CareerProfile).filter(CareerProfile.user_id == user.id).first()
        if not profile:
            profile = CareerProfile(
                user_id=user.id,
                personal={"name": "Alex Mercer", "email": "alex@example.com"},
                professional={"title": "Senior AI Engineer"},
                skills={"technical": ["Python", "FastAPI", "PyTorch", "OpenAI SDK", "Next.js"]},
                experience=[{"title": "AI Developer", "years": 3}]
            )
            db.add(profile)
            db.commit()

        job = db.query(Job).filter(Job.title == "Lead AI Architect").first()
        if not job:
            job = Job(
                title="Lead AI Architect",
                company="NeuralTech Solutions",
                location="Remote",
                remote=True,
                description="Seeking AI Architect with Python, FastAPI, and PyTorch expertise.",
                requirements=["Python", "FastAPI", "PyTorch"],
                application_url="https://neuraltech.example.com/careers/lead-ai"
            )
            db.add(job)
            db.commit()
            db.refresh(job)

        company = db.query(Company).filter(Company.name == "NeuralTech Solutions").first()
        if not company:
            company = Company(name="NeuralTech Solutions", official_website="https://neuraltech.example.com")
            db.add(company)
            db.commit()
            db.refresh(company)

        return user.id, job.id, company.id
    finally:
        db.close()

def test_phase4_complete_workspace_flow():
    user_id, job_id, company_id = setup_phase4_fixtures()
    token = create_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Company Research API
    r_res = client.post(f"/companies/{company_id}/research", headers=headers)
    assert r_res.status_code == 200
    research = r_res.json()
    assert "overview" in research
    assert "claims" in research
    assert len(research["claims"]) > 0

    # 2. Get Company Info
    r_comp = client.get(f"/companies/{company_id}", headers=headers)
    assert r_comp.status_code == 200
    assert r_comp.json()["name"] == "NeuralTech Solutions"

    # 3. Create Application Workspace
    r_app = client.post("/applications", json={"job_id": job_id, "company_id": company_id}, headers=headers)
    assert r_app.status_code == 200
    app_data = r_app.json()
    app_id = app_data["id"]

    # 4. Generate Application Email in all 5 Tones
    for tone in ["Formal", "Technical", "Concise", "Networking", "Cold Outreach"]:
        r_email = client.post(f"/applications/{app_id}/generate-email", json={"tone": tone}, headers=headers)
        assert r_email.status_code == 200
        email_res = r_email.json()
        assert email_res["tone"] == tone
        assert "subject" in email_res
        assert "body" in email_res
        assert len(email_res["referenced_profile_facts"]) > 0

    # 5. Update / Edit Email
    r_edit = client.put(
        f"/applications/{app_id}/email",
        json={"subject": "Customized Subject for NeuralTech", "body": "Customized body text."},
        headers=headers
    )
    assert r_edit.status_code == 200
    assert r_edit.json()["subject"] == "Customized Subject for NeuralTech"

    # 6. Check Gmail OAuth Status & Start
    r_gstatus = client.get("/gmail/status", headers=headers)
    assert r_gstatus.status_code == 200

    r_gstart = client.get("/gmail/oauth/start", headers=headers)
    assert r_gstart.status_code == 200
    assert "oauth_url" in r_gstart.json()

    # 7. Create Gmail Draft - Mandatory Approval Fail Check (user_confirmed=False)
    r_fail_draft = client.post(
        f"/applications/{app_id}/gmail-draft",
        json={"recipient": "careers@neuraltech.example.com", "subject": "Test", "body": "Test", "user_confirmed": False},
        headers=headers
    )
    assert r_fail_draft.status_code == 400

    # 8. Create Gmail Draft with Explicit Approval but no Gmail connection:
    #    must fail honestly — no fake success, no fake draft id.
    r_draft = client.post(
        f"/applications/{app_id}/gmail-draft",
        json={
            "recipient": "careers@neuraltech.example.com",
            "subject": "Customized Subject for NeuralTech",
            "body": "Customized body text.",
            "user_confirmed": True,
            "include_attachment": True
        },
        headers=headers
    )
    assert r_draft.status_code == 409
    assert "draft_id" not in r_draft.json()

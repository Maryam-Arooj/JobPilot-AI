import json
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from fastapi.testclient import TestClient
from backend.api.main import app
from backend.services.auth_service import create_token
from backend.db.database import SessionLocal
from backend.models.career_profile import CareerProfile, User
from backend.models.jobs import Job

client = TestClient(app)
LLM = "backend.services.resume_tailor.call_nvidia_llm"

CV = {
    "title": "Data Engineer",
    "summary": "Data engineer building batch pipelines with Python and SQL.",
    "experience": [
        {"role": "Data Engineer", "company": "Northwind Analytics", "period": "2022 — Present",
         "bullets": ["Rebuilt the ingestion layer on Airflow, cutting load time by 40%.",
                     "Owned the warehouse CI checks."]},
    ],
    "skills": ["SQL", "Python", "Airflow"],
    "education": [{"degree": "BS Computer Science", "institution": "FAST NUCES", "year": "2019"}],
    "certifications": ["AWS Certified Data Engineer"],
}


def _user(email):
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == email).first()
        if not u:
            u = User(email=email, password_hash="hash")
            db.add(u); db.commit(); db.refresh(u)
            db.add(CareerProfile(user_id=u.id, personal={"name": "Tailor Test"}, professional={}))
            db.commit()
        return {"Authorization": f"Bearer {create_token(u.id)}"}
    finally:
        db.close()


def _post(headers, **overrides):
    body = {"target_role": "AI Engineer", "cv": CV}
    body.update(overrides)
    return client.post("/resumes/tailor", json=body, headers=headers)


def test_tailor_requires_auth():
    assert client.post("/resumes/tailor", json={"target_role": "AI Engineer", "cv": CV}).status_code == 401


def test_tailor_requires_target_role():
    h = _user("tailor@test.com")
    assert _post(h, target_role="   ").status_code == 422


def test_tailor_strips_invented_employer_cert_and_skills():
    h = _user("tailor@test.com")
    llm = {
        "title": "AI Engineer",
        "summary": "Data engineer moving into AI, building Python and SQL pipelines.",
        "skills_order": ["Python", "PyTorch", "SQL", "Airflow"],
        "experience": [
            {"index": 0, "bullets": ["Rebuilt the Airflow ingestion layer, cutting load time by 40%.",
                                     "Owned CI checks for the warehouse."]},
            {"index": 0, "company": "Google", "bullets": ["Led ML research at Google."]},
            {"index": 5, "company": "OpenAI", "role": "ML Engineer", "bullets": ["Trained LLMs."]},
        ],
        "certifications": ["Google Professional ML Engineer"],
        "gaps": ["PyTorch", "Python"],
        "notes": ["Reordered skills for AI roles."],
    }
    with mock.patch(LLM, return_value=json.dumps(llm)) as m:
        r = _post(h, job_description="We need PyTorch and Python.")
    assert r.status_code == 200, r.text
    m.assert_called_once()
    assert m.call_args.kwargs["timeout"] == 45
    data = r.json()
    dumped = json.dumps(data)
    assert set(data) == {"title", "summary", "skills_order", "experience", "gaps", "notes"}
    # invented skill dropped; all real skills kept
    assert data["skills_order"] == ["Python", "SQL", "Airflow"]
    # invented employers/entries never reach the experience proposals
    assert "Google" not in json.dumps(data["experience"]) and "OpenAI" not in json.dumps(data["experience"])
    assert data["experience"] == [{"index": 0, "bullets": llm["experience"][0]["bullets"]}]
    # invented certification is not returned anywhere as a CV change
    assert "Google Professional ML Engineer" not in dumped
    # gaps contain only what the CV lacks; Python is already in the CV
    assert data["gaps"] == ["PyTorch"]


def test_tailor_rejects_ungrounded_free_text():
    h = _user("tailor@test.com")
    llm = {
        "title": "AI Engineer",
        "summary": "AI engineer with PyTorch experience who led ML at Meta.",
        "skills_order": ["Python"],
        "experience": [{"index": 0, "bullets": [
            "Rebuilt the ingestion layer, cutting load time by 75%.",
            "Owned the warehouse CI checks as an AWS Certified ML Specialist."]}],
        "gaps": ["PyTorch"],
    }
    with mock.patch(LLM, return_value="```json\n" + json.dumps(llm) + "\n```"):
        r = _post(h)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["summary"] == CV["summary"]           # claimed a gap + named employer -> original kept
    assert data["experience"] == []                   # invented metric and certification -> originals kept
    assert data["skills_order"] == ["Python", "SQL", "Airflow"]
    assert any("75" in n for n in data["notes"])


def test_tailor_503_when_llm_unreachable():
    h = _user("tailor@test.com")
    with mock.patch(LLM, side_effect=RuntimeError("NVIDIA LLM service error: https://integrate.api.nvidia.com key=nvapi-SECRET")):
        r = _post(h)
    assert r.status_code == 503
    assert "could not be reached" in r.json()["detail"]
    assert "nvapi" not in r.text and "nvidia.com" not in r.text
    with mock.patch(LLM, return_value=""):           # no API key configured
        assert _post(h).status_code == 503


def test_tailor_503_on_invalid_json():
    h = _user("tailor@test.com")
    with mock.patch(LLM, return_value="Sure! Here is your tailored CV: title AI Engineer"):
        r = _post(h)
    assert r.status_code == 503
    assert "could not be used" in r.json()["detail"]


def test_tailor_job_id_must_belong_to_user():
    h = _user("tailor@test.com")
    db = SessionLocal()
    try:
        job = Job(title="AI Engineer", company="SomeCo", description="PyTorch", requirements=[], technologies=[])
        db.add(job); db.commit(); db.refresh(job)
        job_id = job.id
    finally:
        db.close()
    with mock.patch(LLM, return_value="{}") as m:
        r = _post(h, job_id=job_id)
    assert r.status_code == 404
    m.assert_not_called()

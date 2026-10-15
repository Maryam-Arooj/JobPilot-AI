import pytest
from fastapi.testclient import TestClient
from backend.api.main import app
from backend.services.auth_service import create_token
from backend.db.database import get_db, SessionLocal
from backend.models.career_profile import User, CareerProfile

client = TestClient(app)

def setup_test_user_and_profile():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "jobstest@example.com").first()
        if not user:
            user = User(email="jobstest@example.com", password_hash="hashedpass")
            db.add(user)
            db.commit()
            db.refresh(user)

        profile = db.query(CareerProfile).filter(CareerProfile.user_id == user.id).first()
        if not profile:
            profile = CareerProfile(
                user_id=user.id,
                professional={"title": "AI Engineer"},
                skills={"technical": ["Python", "FastAPI", "OpenAI", "PyTorch"]},
                experience=[{"title": "Software Engineer", "years": 2}],
                education=[{"degree": "BS Computer Science"}]
            )
            db.add(profile)
            db.commit()
        return user.id
    finally:
        db.close()

def test_jobs_phase3_complete_api_flow():
    user_id = setup_test_user_and_profile()
    token = create_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. POST /jobs/search
    r_search = client.post("/jobs/search?query=Find+remote+AI+Engineer+jobs", headers=headers)
    assert r_search.status_code == 200
    search_data = r_search.json()
    assert "intent" in search_data
    assert "results" in search_data
    assert len(search_data["results"]) > 0

    job_id = search_data["results"][0]["id"]

    # 2. GET /jobs
    r_list = client.get("/jobs", headers=headers)
    assert r_list.status_code == 200
    jobs_list = r_list.json()
    assert len(jobs_list) > 0

    # 3. GET /jobs/{id}
    r_get = client.get(f"/jobs/{job_id}", headers=headers)
    assert r_get.status_code == 200
    job_detail = r_get.json()
    assert job_detail["id"] == job_id
    assert "title" in job_detail

    # 4. POST /jobs/{id}/analyze
    r_analyze = client.post(f"/jobs/{job_id}/analyze", headers=headers)
    assert r_analyze.status_code == 200
    analysis = r_analyze.json()
    assert "required_skills" in analysis

    # 5. POST /jobs/{id}/match
    r_match = client.post(f"/jobs/{job_id}/match", headers=headers)
    assert r_match.status_code == 200
    match_res = r_match.json()
    assert "overall_alignment" in match_res
    assert match_res["overall_alignment"] in ["Strong Alignment", "Review", "Limited Alignment"]
    assert "evidence" in match_res
    assert len(match_res["evidence"]) > 0

    # Verify evidence item format
    ev = match_res["evidence"][0]
    assert "explanation" in ev
    assert "career_profile_fact_path" in ev

    # 6. GET /jobs/{id}/sources
    r_sources = client.get(f"/jobs/{job_id}/sources", headers=headers)
    assert r_sources.status_code == 200
    sources = r_sources.json()
    assert isinstance(sources, list)

    # 7. GET /jobs/{id}/match
    r_get_match = client.get(f"/jobs/{job_id}/match", headers=headers)
    assert r_get_match.status_code == 200
    saved_match = r_get_match.json()
    assert saved_match["overall_alignment"] == match_res["overall_alignment"]

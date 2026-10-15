import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from fastapi.testclient import TestClient
from backend.api.main import app
from backend.services.auth_service import create_token
from backend.db.database import SessionLocal
from backend.models.career_profile import CareerProfile, User
from backend.models.resume import ResumeDocument

client = TestClient(app)

def setup_user():
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == "resume@test.com").first()
        if not u:
            u = User(email="resume@test.com", password_hash="hash")
            db.add(u)
            db.commit()
            db.refresh(u)
        uid = u.id
        profile = db.query(CareerProfile).filter(CareerProfile.user_id == uid).first()
        if not profile:
            profile = CareerProfile(user_id=uid, personal={"name":"Test User","email":"resume@test.com"}, professional={"title":"Engineer"}, experience=[{"role":"Engineer"}])
            db.add(profile)
            db.commit()
        return uid
    finally:
        db.close()

def test_resume_flow():
    user_id = setup_user()
    token = create_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}
    # create resume
    r = client.post("/resumes/", json={"template":"ATS","title":"Test Resume"}, headers=headers)
    assert r.status_code == 200
    resume_id = r.json()["id"]
    # generate
    r = client.post(f"/resumes/{resume_id}/generate", json={"target_role":"AI Engineer"}, headers=headers)
    assert r.status_code == 200
    version_id = r.json()["version_id"]
    # quality check
    r = client.post(f"/resumes/{resume_id}/quality-check", headers=headers)
    assert r.status_code == 200
    report = r.json()
    assert "status" in report
    # approve
    r = client.post(f"/resumes/{resume_id}/approve", headers=headers)
    assert r.status_code == 200
    # export pdf should work
    r = client.post(f"/resumes/{resume_id}/export/pdf", headers=headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    # export docx
    r = client.post(f"/resumes/{resume_id}/export/docx", headers=headers)
    assert r.status_code == 200

if __name__ == "__main__":
    test_resume_flow()
    print("Resume Phase2 tests passed")

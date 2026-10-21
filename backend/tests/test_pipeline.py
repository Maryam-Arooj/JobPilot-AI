"""Task 5 — one-click pipeline: CV -> jobs -> recruiter email -> best match -> application, stops for approval."""
import sys
import time
import uuid
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.db.database import SessionLocal
from backend.models.career_profile import CareerProfile, User
from backend.models.jobs import Job
from backend.services import recipients
from backend.services.auth_service import create_token

client = TestClient(app)


def _setup():
    db = SessionLocal()
    u = User(email=f"p-{uuid.uuid4().hex[:6]}@test.local", password_hash="x"); db.add(u); db.commit(); db.refresh(u)
    db.add(CareerProfile(user_id=u.id, personal={"name": "Jordan Avery"}, professional={"headline": "Data Engineer"},
                         skills={"technical": ["Python", "SQL"]}, experience=[]))
    a = Job(title="Data Engineer", company=f"NoMail {uuid.uuid4().hex[:4]}", description="Python, SQL")
    b = Job(title="Python Developer", company=f"HasMail {uuid.uuid4().hex[:4]}", description="Python. CVs to hr@hasmail.pk")
    db.add_all([a, b]); db.commit()
    ids = (u.id, a.id, b.id, a.company, b.company)
    db.close()
    return ids


def _wait(pid, h):
    for _ in range(100):
        s = client.get(f"/pipeline/{pid}", headers=h).json()
        if s["status"] != "running":
            return s
        time.sleep(0.1)
    return s


def test_pipeline_picks_best_job_with_email_and_stops_for_approval():
    uid, a, b, ca, cb = _setup()
    h = {"Authorization": f"Bearer {create_token(uid)}"}
    ranked = {"query": "Data Engineer", "searched": "Pakistan", "results": [
        {"id": a, "title": "Data Engineer", "company": ca, "match_score": 90},
        {"id": b, "title": "Python Developer", "company": cb, "match_score": 70}]}
    none = {"contacts": [], "checked": [], "message": "none"}
    created = {"id": 777, "company": {"research": {"status": "not_found"}}, "cv_attachment": {"label": "CV built from your saved profile"}}
    with mock.patch("backend.api.jobs.jobs_from_cv", return_value=ranked), \
         mock.patch.object(recipients, "search_recipients", return_value=none), \
         mock.patch("backend.api.applications.create_application", return_value=created) as ca_mock:
        pid = client.post("/pipeline/apply", json={"location": "Pakistan", "mode": "location"}, headers=h).json()["pipeline_id"]
        s = _wait(pid, h)
    assert s["status"] == "ready", s
    assert s["job"]["id"] == b and s["recipient"] == "hr@hasmail.pk"      # best job WITH an email, not the 90% one
    assert s["application_id"] == 777 and ca_mock.call_args.args[0].job_id == b
    assert [x["status"] for x in s["steps"]] == ["done"] * 5 + ["waiting"]  # never creates the Gmail draft itself


def test_pipeline_stops_honestly_when_no_job_has_an_email():
    uid, a, _b, ca, _cb = _setup()
    h = {"Authorization": f"Bearer {create_token(uid)}"}
    ranked = {"query": "Data Engineer", "searched": "Remote", "results": [{"id": a, "title": "Data Engineer", "company": ca, "match_score": 90}]}
    with mock.patch("backend.api.jobs.jobs_from_cv", return_value=ranked), \
         mock.patch.object(recipients, "search_recipients", return_value={"contacts": [], "checked": [], "message": ""}):
        pid = client.post("/pipeline/apply", json={"mode": "remote"}, headers=h).json()["pipeline_id"]
        s = _wait(pid, h)
    assert s["status"] == "failed" and "publish a recruiter email" in s["error"]
    assert s["steps"][3]["status"] == "failed" and s["application_id"] is None


def test_pipeline_needs_a_cv():
    db = SessionLocal()
    u = User(email=f"n-{uuid.uuid4().hex[:6]}@test.local", password_hash="x"); db.add(u); db.commit(); db.refresh(u)
    uid = u.id; db.close()
    h = {"Authorization": f"Bearer {create_token(uid)}"}
    pid = client.post("/pipeline/apply", json={}, headers=h).json()["pipeline_id"]
    s = _wait(pid, h)
    assert s["status"] == "failed" and "Upload your CV" in s["error"]

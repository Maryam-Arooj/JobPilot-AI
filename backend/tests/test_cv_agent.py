"""Task 2 — CV Agent: grounded extraction, honest fallback, review-before-verify, profile/resume fixes."""
import json
import sys
import uuid
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from fastapi.testclient import TestClient

from backend.ai_agents import profile_agent as pa
from backend.api.main import app
from backend.db.database import SessionLocal
from backend.models.career_profile import CareerProfile, ProfileFact, User
from backend.services import nvidia_llm
from backend.services.auth_service import create_token

client = TestClient(app)

CV = """Jordan Avery
Senior Data Engineer
jordan.avery@example.com | +1 555 0100 2233 | Austin, TX
SUMMARY
Data engineer with 7 years of experience building batch and streaming pipelines.
EXPERIENCE
Northwind Analytics - Senior Data Engineer (2021 - Present)
Built Airflow and Spark pipelines on AWS; cut warehouse load time by 40%.
Contoso Retail - Data Engineer (2018 - 2021)
Maintained PostgreSQL and Python ETL jobs.
EDUCATION
University of Texas at Austin - BS Computer Science (2018)
SKILLS
Python, SQL, Airflow, Spark, AWS, PostgreSQL, Docker
"""

LLM_OUTPUT = {
    "personal": {"name": "Jordan Avery", "email": "jordan.avery@example.com", "phone": "+1 555 0100 2233",
                 "location": "Austin, TX", "linkedin": "linkedin.com/in/jordan-avery-invented", "github": "", "website": ""},
    "professional": {"headline": "Senior Data Engineer",
                     "summary": "Data engineer with 7 years of experience building batch and streaming pipelines."},
    "skills": {"technical": ["Python", "SQL", "Kubernetes"], "frameworks": ["Spark", "Airflow"], "tools": ["AWS", "Docker", "Python"], "soft": []},
    "experience": [
        {"title": "Senior Data Engineer", "company": "Northwind Analytics", "location": "", "start_date": "2021", "end_date": "Present",
         "description": "Built Airflow and Spark pipelines on AWS; cut warehouse load time by 40%."},
        {"title": "Data Engineer", "company": "Contoso Retail", "location": "", "start_date": "2018", "end_date": "2021",
         "description": "Led a team of 12 engineers at a Fortune 500 bank."},
        {"title": "Staff Engineer", "company": "Google", "location": "", "start_date": "2015", "end_date": "2018", "description": ""},
    ],
    "education": [{"degree": "BS Computer Science", "institution": "University of Texas at Austin", "location": "", "year": "2018"},
                  {"degree": "Bachelor of Science", "institution": "MIT", "location": "", "year": "2023"}],
    "projects": [],
    "certifications": ["AWS Certified Solutions Architect"],
    "languages": [],
}

INVENTED = ["Kubernetes", "Google", "Staff Engineer", "MIT", "Bachelor of Science", "2023",
            "AWS Certified Solutions Architect", "jordan-avery-invented", "Fortune 500"]


def _user():
    db = SessionLocal()
    try:
        u = User(email=f"cv-{uuid.uuid4().hex[:8]}@test.local", password_hash="x")
        db.add(u); db.commit(); db.refresh(u)
        return u.id, {"Authorization": f"Bearer {create_token(u.id)}"}
    finally:
        db.close()


def _profile(uid):
    db = SessionLocal()
    try:
        p = db.query(CareerProfile).filter(CareerProfile.user_id == uid).first()
        facts = db.query(ProfileFact).filter(ProfileFact.profile_id == p.id).all() if p else []
        return p, facts
    finally:
        db.close()


# ---------------- extraction ----------------

def test_llm_extraction_is_grounded_and_invented_values_are_dropped():
    with mock.patch.object(pa, "call_nvidia_json", return_value=json.loads(json.dumps(LLM_OUTPUT))):
        out = pa.ProfileAgent().extract_from_text(CV)
    assert out["extraction_method"] == "llm"
    blob = json.dumps(out["profile_data"])
    for bad in INVENTED:
        assert bad not in blob, bad
    p = out["profile_data"]
    assert p["personal"]["name"] == "Jordan Avery" and p["personal"]["phone"] == "+1 555 0100 2233"
    assert [e["company"] for e in p["experience"]] == ["Northwind Analytics", "Contoso Retail"]
    assert "description" not in p["experience"][1]          # invented bullet removed, entry kept
    assert p["professional"]["experience_years"] == 7         # the CV's own statement, not a guess
    assert p["education"] == [{"degree": "BS Computer Science", "institution": "University of Texas at Austin", "year": "2018"}]
    flat = pa.flatten_skills(p["skills"])
    assert sorted(flat) == sorted(["Python", "SQL", "Spark", "Airflow", "AWS", "Docker"])  # once each
    assert len(out["dropped"]) >= len(INVENTED) - 1
    assert all(f["verified"] is False for f in out["facts"])
    assert {"experience[0]", "experience[1]", "education[0]", "skills", "personal.name"} <= {f["path"] for f in out["facts"]}


def test_years_are_computed_from_dates_when_not_stated():
    cv = CV.replace("with 7 years of experience ", "")
    data = json.loads(json.dumps(LLM_OUTPUT)); data["professional"]["summary"] = ""
    with mock.patch.object(pa, "call_nvidia_json", return_value=data):
        p = pa.ProfileAgent().extract_from_text(cv)["profile_data"]
    from datetime import date
    assert p["experience"][1]["years"] == 3.0
    assert p["professional"]["experience_years"] == (date.today().year - 2021) + 3


def test_truncated_json_is_an_error_not_a_result(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "nvapi-test")
    resp = mock.Mock(status_code=200)
    resp.json.return_value = {"choices": [{"finish_reason": "length", "message": {"content": '{"personal": {"name": "Jor'}}]}
    with mock.patch.object(nvidia_llm.requests, "post", return_value=resp):
        with pytest.raises(nvidia_llm.LLMResponseError, match="cut off"):
            nvidia_llm.call_nvidia_json("x", model_override="m")


def test_fallback_copies_only_literal_text_and_never_invents():
    with mock.patch.object(pa, "call_nvidia_json", side_effect=nvidia_llm.LLMUnavailableError("timed out")):
        out = pa.ProfileAgent().extract_from_text(CV)
    assert out["extraction_method"] == "fallback_partial" and "unavailable" in out["message"]
    p = out["profile_data"]
    assert p["personal"]["email"] == "jordan.avery@example.com"
    assert p["personal"]["name"] == "Jordan Avery"
    assert p["personal"]["location"] == "Austin, TX"
    assert p["professional"]["headline"] == "Senior Data Engineer"
    assert p["professional"]["experience_years"] == 7
    assert p["experience"] == [] and p["education"] == []
    assert {"experience", "education"} <= set(out["missing_fields"])
    blob = json.dumps(p)
    for bad in ["Bachelor of Science", "2023", "Tech Company", "Professional Experience", "Software Engineer",
                "Led development", "Specialist", "Production project delivery"]:
        assert bad not in blob, bad
    for s in ["Python", "SQL", "Airflow", "Spark", "AWS", "PostgreSQL", "Docker"]:
        assert s in pa.flatten_skills(p["skills"])
    assert all(f["verified"] is False for f in out["facts"])


def test_fallback_on_minimal_text_invents_nothing():
    with mock.patch.object(pa, "call_nvidia_json", side_effect=nvidia_llm.LLMUnavailableError("down")):
        out = pa.ProfileAgent().extract_from_text("I'm a BS Data Science student")
    p = out["profile_data"]
    assert p["experience"] == [] and p["education"] == [] and not p["personal"]
    assert "experience_years" not in p["professional"]


def test_empty_text_is_reported():
    out = pa.ProfileAgent().extract_from_text("   ")
    assert out["extraction_method"] == "none" and out["facts"] == []


def test_normalize_skills_removes_overlapping_categories():
    s = pa.normalize_skills({"technical": ["Python", "React", "Docker"], "frameworks": ["React"], "tools": ["docker", "Git"]})
    assert pa.flatten_skills(s) == ["React", "docker", "Git", "Python"] or sorted(map(str.lower, pa.flatten_skills(s))) == ["docker", "git", "python", "react"]
    assert len(pa.flatten_skills(s)) == 4


# ---------------- endpoints ----------------

def _upload(headers, text=CV, route="/documents/upload", llm=LLM_OUTPUT):
    with mock.patch.object(pa, "call_nvidia_json", return_value=json.loads(json.dumps(llm))):
        return client.post(route, headers=headers, files={"file": ("cv.txt", text.encode(), "text/plain")})


def test_upload_saves_grounded_profile_with_unverified_facts_then_confirm_verifies():
    uid, headers = _user()
    r = _upload(headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["extraction_method"] == "llm" and body["needs_review"] == len(body["facts"]) > 0
    profile, facts = _profile(uid)
    assert facts and all(not f.verified for f in facts)
    assert profile.personal["name"] == "Jordan Avery"
    assert "Google" not in json.dumps(profile.experience)
    assert profile.professional["experience_years"] == 7
    ids = [f["id"] for f in body["facts"]]
    c = client.post("/profiles/me/facts/confirm", headers=headers, json={"fact_ids": ids, "action": "confirm"})
    assert c.status_code == 200 and c.json()["confirmed"] == len(ids)
    _, facts = _profile(uid)
    assert all(f.verified for f in facts)


def test_reupload_never_overwrites_a_confirmed_value():
    uid, headers = _user()
    body = _upload(headers).json()
    name_fact = next(f for f in body["facts"] if f["path"] == "personal.name")
    client.post("/profiles/me/facts/confirm", headers=headers, json={"fact_ids": [name_fact["id"]], "action": "confirm"})
    cv2 = CV.replace("Jordan Avery", "Jordan A. Avery")
    llm2 = json.loads(json.dumps(LLM_OUTPUT)); llm2["personal"]["name"] = "Jordan A. Avery"
    r = _upload(headers, text=cv2, llm=llm2)
    assert "personal.name" in r.json()["conflicts"]
    profile, facts = _profile(uid)
    assert profile.personal["name"] == "Jordan Avery"
    name_rows = [f for f in facts if f.path == "personal.name"]
    assert {(f.value, f.verified) for f in name_rows} == {("Jordan Avery", True), ("Jordan A. Avery", False)}


def test_parse_does_not_save_and_reports_method():
    uid, headers = _user()
    r = _upload(headers, route="/documents/parse")
    assert r.status_code == 200 and r.json()["extraction_method"] == "llm"
    assert r.json()["dropped"]
    assert _profile(uid)[0] is None


def test_profile_extract_upload_route_and_text_route():
    uid, headers = _user()
    r = _upload(headers, route="/profiles/me/extract/upload")
    assert r.status_code == 200 and r.json()["needs_review"] > 0
    with mock.patch.object(pa, "call_nvidia_json", side_effect=nvidia_llm.LLMUnavailableError("down")):
        r2 = client.post("/profiles/me/extract", headers=headers, json={"text": CV, "auto_save": False})
    assert r2.json()["extraction_method"] == "fallback_partial" and r2.json()["saved_to_profile"] is False


def test_sync_profile_skips_rejected_entries_and_verifies_confirmed_facts():
    uid, headers = _user()
    parsed = _upload(headers, route="/documents/parse").json()
    kept = [f for f in parsed["facts"] if f["path"] != "experience[1]"]  # user rejected the 2nd job
    r = client.post("/documents/sync-profile", headers=headers, json={"profile_data": parsed["profile_data"], "facts": kept})
    assert r.status_code == 200
    profile, facts = _profile(uid)
    assert [e["company"] for e in profile.experience] == ["Northwind Analytics"]
    assert facts and all(f.verified for f in facts)
    assert len(pa.flatten_skills(profile.skills)) == len(set(map(str.lower, pa.flatten_skills(profile.skills))))


def test_edit_profile_keeps_fields_the_form_does_not_send():
    uid, headers = _user()
    _upload(headers)
    r = client.put("/profiles/me", headers=headers, json={
        "personal": {"name": "Jordan Avery", "location": "Dallas, TX"},
        "professional": {"summary": "Updated summary", "skills": ["Python", "SQL", "python"]}})
    assert r.status_code == 200
    profile, _ = _profile(uid)
    assert profile.personal["phone"] == "+1 555 0100 2233"           # not sent -> kept
    assert profile.personal["location"] == "Dallas, TX"
    assert profile.professional["headline"] == "Senior Data Engineer"  # not sent -> kept
    assert profile.professional["skills"] == ["Python", "SQL"]
    r = client.put("/profiles/me", headers=headers, json={"personal": {"phone": ""}})
    assert "phone" not in _profile(uid)[0].personal                   # "" clears explicitly


def test_save_version_keeps_the_editor_content():
    uid, headers = _user()
    _upload(headers)
    res = client.post("/resumes/", headers=headers, json={"title": "Mine", "template": "ATS Clean", "target_role": "Data Engineer"}).json()
    edited = {"title": "Lead Data Engineer", "name": "Jordan Avery", "summary": "My own edited summary.",
              "experience": [{"role": "Senior Data Engineer", "company": "Northwind Analytics", "period": "2021 — Present",
                              "bullets": ["Edited bullet I wrote myself."]}],
              "education": [], "skills": ["Python", "SQL"], "certifications": []}
    r = client.post(f"/resumes/{res['id']}/generate", headers=headers,
                    json={"template": "ATS Clean", "target_role": "Data Engineer", "custom_content": edited})
    assert r.status_code == 200
    snap = r.json()["content_snapshot"]
    assert snap["summary"] == "My own edited summary." and snap["experience"][0]["bullets"] == ["Edited bullet I wrote myself."]
    listed = client.get(f"/resumes/{res['id']}", headers=headers).json()
    assert "My own edited summary." in json.dumps(listed)
    pdf = client.get(f"/resumes/{res['id']}/export/pdf", headers=headers)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"

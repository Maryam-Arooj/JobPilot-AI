"""Task 3 — Job Agent: real provider mapping, parallel discovery, honest scoring, CV → recommended jobs."""
import json
import sys
import uuid
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.db.database import SessionLocal
from backend.models.career_profile import CareerProfile, User
from backend.providers import apify_job_source as apify_mod, serp_job_search as serp_mod
from backend.services import job_matching as jm
from backend.services.auth_service import create_token
from backend.services.job_normalizer import normalize_job

client = TestClient(app)

SERP_RESULTS = {"jobs_results": [
    {"title": "Data Engineer", "company_name": "Acme Analytics", "location": "Lahore, Pakistan", "via": "LinkedIn",
     "description": "We need a data engineer with Python, SQL and Airflow. 3+ years of experience.",
     "job_highlights": [{"title": "Qualifications", "items": ["Python and SQL", "Experience with Airflow", "Kafka is a plus"]},
                        {"title": "Responsibilities", "items": ["Build pipelines"]}],
     "apply_options": [{"title": "Company site", "link": "https://acme.example/jobs/1?utm_source=x"}],
     "detected_extensions": {"schedule_type": "Full-time", "posted_at": "2 days ago"}, "job_id": "abc"},
    {"title": "Office Assistant", "company_name": "Beta Co", "location": "Lahore, Pakistan",
     "description": "Friendly team member wanted.", "share_link": "https://google.example/share/2"},
]}
APIFY_ITEMS = [
    {"title": "Senior Data Engineer", "companyName": "Contoso", "location": "Lahore, Punjab, Pakistan",
     "descriptionText": "Spark, AWS and Python. 5+ years.", "link": "https://linkedin.example/jobs/9", "seniorityLevel": "Mid-Senior level"},
    {"error": "Input is not valid: something went wrong"},
    {"title": "", "companyName": "Nobody"},
]
PROFILE = {
    "personal": {"name": "Jordan Avery", "location": "Lahore, Pakistan"},
    "professional": {"headline": "Data Engineer | Python Developer", "experience_years": 4,
                     "skills": ["Python", "SQL", "Airflow", "Docker"]},
    "skills": {"technical": ["Python", "SQL", "Airflow", "Docker"]},
    "experience": [{"title": "Data Engineer", "company": "Northwind", "years": 4}],
}


def _resp(status, data):
    r = mock.Mock(status_code=status)
    r.json.return_value = data
    return r


def _user(with_profile=True):
    db = SessionLocal()
    try:
        u = User(email=f"job-{uuid.uuid4().hex[:8]}@test.local", password_hash="x")
        db.add(u); db.commit(); db.refresh(u)
        if with_profile:
            db.add(CareerProfile(user_id=u.id, **{k: v for k, v in PROFILE.items()})); db.commit()
        return u.id, {"Authorization": f"Bearer {create_token(u.id)}"}
    finally:
        db.close()


@pytest.fixture
def providers(monkeypatch):
    monkeypatch.setenv("SERPAPI_KEY", "test-serp")
    monkeypatch.setenv("APIFY_API_TOKEN", "test-apify")
    calls = {"serp": [], "apify": []}

    def serp_get(url, params=None, timeout=None):
        calls["serp"].append(dict(params))
        return _resp(200, SERP_RESULTS)

    def apify_post(url, params=None, json=None, timeout=None):
        calls["apify"].append(dict(json))
        return _resp(201, APIFY_ITEMS)
    with mock.patch.object(serp_mod.requests, "get", side_effect=serp_get), \
         mock.patch.object(apify_mod.requests, "post", side_effect=apify_post):
        yield calls


# ---------------- provider mapping ----------------

def test_serp_job_is_mapped_from_real_google_jobs_fields():
    j = serp_mod.adapt_serp_job(SERP_RESULTS["jobs_results"][0])
    assert j["company"] == "Acme Analytics" and j["application_url"].startswith("https://acme.example/jobs/1")
    assert j["requirements"] == ["Python and SQL", "Experience with Airflow", "Kafka is a plus"]
    assert j["responsibilities"] == ["Build pipelines"] and j["employment_type"] == "Full-time"
    assert serp_mod.adapt_serp_job({"title": "x"}) is None


def test_serp_retries_with_location_in_query_when_google_rejects_location(monkeypatch):
    monkeypatch.setenv("SERPAPI_KEY", "k")
    answers = [_resp(200, {"error": "Google hasn't returned any results for this query."}), _resp(200, SERP_RESULTS)]
    with mock.patch.object(serp_mod.requests, "get", side_effect=answers) as get:
        jobs = serp_mod.SerpJobSearchProvider().search("Data Engineer", {"location": "Lahore, Pakistan"})
    assert len(jobs) == 2
    first, second = get.call_args_list[0].kwargs["params"], get.call_args_list[1].kwargs["params"]
    assert first["location"] == "Lahore, Pakistan" and "location" not in second and "Lahore" in second["q"]


def test_apify_uses_keywords_and_location_and_skips_error_items(providers):
    jobs = apify_mod.ApifyJobSource().search("Data Engineer", {"location": "Lahore, Pakistan"})
    payload = providers["apify"][0]
    assert payload["keywords"] == "Data Engineer" and payload["location"] == "Lahore, Pakistan"
    assert "queries" not in payload and payload["limitPerSource"] == 10
    assert [j["company"] for j in jobs] == ["Contoso"]


def test_normalizer_invents_no_defaults():
    n = normalize_job({"title": "X", "company": "Y"}, "test")
    assert n["employment_type"] is None and n["seniority"] is None and n["industry"] is None and n["job_type"] is None


# ---------------- honest scoring ----------------

def test_score_counts_only_skills_written_in_the_job():
    job = {"title": "Data Engineer", "description": "Python, SQL, Airflow and Kafka. 3+ years of experience.", "requirements": []}
    s = jm.score_job(PROFILE, job)
    assert set(s["matched_skills"]) == {"Python", "SQL", "Airflow"} and s["missing_skills"] == ["Kafka"]
    assert "Docker" not in s["matched_skills"]          # in the CV but not in the job
    assert 70 <= s["match_score"] <= 100 and s["alignment"] in ("Strong match", "Good match")
    assert s["required_years"] == 3 and s["candidate_years"] == 4.0


def test_job_without_recognisable_skills_gets_no_score():
    s = jm.score_job(PROFILE, {"title": "Office Assistant", "description": "Friendly team member wanted."})
    assert s["match_score"] is None and s["alignment"] == "Not enough data"


def test_years_gap_lowers_score_and_is_listed():
    low = jm.score_job(PROFILE, {"title": "Data Engineer", "description": "Python and SQL. 8+ years required."})
    assert any("8+ years" in g for g in low["gaps"])


def test_ai_analysis_drops_skills_not_in_the_job(monkeypatch):
    job = {"title": "Data Engineer", "description": "Python and SQL. 3+ years.", "requirements": []}
    fake = {"required_skills": ["Python", "SQL", "Kubernetes"], "preferred_skills": ["Rust"], "min_years": 7,
            "education": "PhD", "seniority": None}
    with mock.patch("backend.services.nvidia_llm.call_nvidia_json", return_value=fake):
        ai = jm.analyze_job_with_ai(job)
    assert ai["required_skills"] == ["Python", "SQL"] and ai["preferred_skills"] == []
    assert ai["min_years"] == 3 and ai["education"] is None


# ---------------- endpoints ----------------

def test_search_runs_both_providers_and_never_saves_error_items(providers):
    _, headers = _user()
    r = client.post("/jobs/search?query=Data%20Engineer&country=Pakistan", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert {j["company"] for j in body["results"]} == {"Acme Analytics", "Beta Co", "Contoso"}
    assert body["provider_status"]["serpapi:google_jobs"]["ok"] and body["provider_status"]["apify:linkedin_jobs"]["jobs"] == 1
    assert body["results"][0]["match_score"] is not None
    assert body["results"][-1]["match_score"] is None   # 'Office Assistant' has no comparable skills
    snap = client.get("/agent-runs/snapshot?range=1h", headers=headers).json()
    run = next(x for x in snap["runs"] if x["agent"] == "job")
    assert {t["name"] for t in run["tool_calls"]} >= {"serpapi:google_jobs", "apify:linkedin_jobs"}


def test_one_provider_failing_still_returns_the_other(monkeypatch, providers):
    with mock.patch.object(apify_mod.requests, "post", return_value=_resp(500, {})):
        _, headers = _user()
        r = client.post("/jobs/search?query=Data%20Engineer", headers=headers)
    assert r.status_code == 200 and len(r.json()["results"]) == 2
    assert r.json()["provider_status"]["apify:linkedin_jobs"]["ok"] is False


def test_jobs_from_uploaded_cv_without_saving_it(providers):
    uid, headers = _user(with_profile=False)
    r = client.post("/jobs/from-cv", headers=headers, json={"profile_data": PROFILE})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["query"] == "Data Engineer" and body["location"] == "Lahore, Pakistan"
    assert providers["serp"][0]["q"] == "Data Engineer"
    scores = [j["match_score"] for j in body["results"] if j["match_score"] is not None]
    assert scores == sorted(scores, reverse=True) and body["results"][0]["matched_skills"]
    db = SessionLocal()
    try:
        assert db.query(CareerProfile).filter(CareerProfile.user_id == uid).first() is None  # CV not saved
    finally:
        db.close()
    rec = client.get("/jobs/recommendations", headers=headers).json()
    assert rec["total_recommendations"] == 3


def test_jobs_from_cv_needs_a_role_or_skills():
    _, headers = _user(with_profile=False)
    r = client.post("/jobs/from-cv", headers=headers, json={"profile_data": {"personal": {"name": "X"}}})
    assert r.status_code == 400


def test_match_endpoint_uses_grounded_ai_and_stores_evidence(providers):
    _, headers = _user()
    jobs = client.post("/jobs/search?query=Data%20Engineer", headers=headers).json()["results"]
    acme = next(j for j in jobs if j["company"] == "Acme Analytics")
    fake = {"required_skills": ["Python", "SQL", "Kubernetes"], "preferred_skills": ["Kafka"], "min_years": 3}
    with mock.patch("backend.services.nvidia_llm.call_nvidia_json", return_value=fake):
        m = client.post(f"/jobs/{acme['id']}/match", headers=headers).json()
    assert m["method"] == "ai" and m["match_score"] is not None
    assert "Kubernetes" not in json.dumps(m)                   # not in the job text -> dropped
    assert set(m["matched_requirements"]) == {"Python", "SQL"} and "Kafka" in m["gaps"]
    stored = client.get(f"/jobs/{acme['id']}/match", headers=headers).json()
    assert stored["evidence"]

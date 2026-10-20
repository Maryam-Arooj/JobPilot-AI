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
    assert 60 <= s["match_score"] <= 100 and s["alignment"] in ("Strong match", "Good match")
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
    status = body["provider_status"]
    assert status["serpapi:google_jobs [Pakistan]"]["ok"] and status["apify:linkedin_jobs [Pakistan]"]["jobs"] == 1
    assert providers["serp"][0]["gl"] == "pk"
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
    assert r.json()["provider_status"]["apify:linkedin_jobs [any]"]["ok"] is False


def test_jobs_from_uploaded_cv_without_saving_it(providers):
    uid, headers = _user(with_profile=False)
    r = client.post("/jobs/from-cv", headers=headers, json={"profile_data": PROFILE})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["query"] == "Data Engineer" and body["location"] == "Lahore, Pakistan"
    assert body["searched"] == "remote + Lahore, Pakistan"
    serp_calls = providers["serp"]
    assert any(c.get("ltype") == "1" for c in serp_calls)                      # remote search (preferred)
    assert any(c.get("location") == "Lahore, Pakistan" and c.get("gl") == "pk" for c in serp_calls)  # Pakistan on-site
    assert all(c["q"].startswith("Data Engineer") for c in serp_calls)
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



def test_remote_search_uses_google_work_from_home_filter(providers):
    _, headers = _user()
    r = client.post("/jobs/search?query=Data%20Engineer&country=Remote%20Worldwide", headers=headers)
    assert r.status_code == 200
    assert providers["serp"][0].get("ltype") == "1" and "location" not in providers["serp"][0]
    assert providers["apify"][0]["keywords"] == "Data Engineer remote" and providers["apify"][0]["location"] == "Worldwide"
    assert all(j["remote"] for j in r.json()["results"])


def test_from_cv_country_mode_searches_only_that_country(providers):
    _, headers = _user()
    r = client.post("/jobs/from-cv", headers=headers, json={"mode": "location", "location": "Pakistan"})
    assert r.status_code == 200 and r.json()["searched"] == "Pakistan"
    assert not any(c.get("ltype") == "1" for c in providers["serp"])


def test_one_matching_skill_is_not_a_strong_match():
    s = jm.score_job(PROFILE, {"title": "Automation Architect", "description": "Experience with Python."})
    assert s["match_score"] is not None and s["match_score"] < 65


def test_generic_words_in_cv_are_not_counted_as_skills():
    prof = {**PROFILE, "professional": {**PROFILE["professional"], "skills": ["Python", "Development", "Software"]}}
    s = jm.score_job(prof, {"title": "Software Engineer", "description": "Development of software with Python and Java."})
    assert "Development" not in s["matched_skills"] and "Software" not in s["matched_skills"]


def test_remote_jobs_are_preferred_within_similar_scores():
    from backend.api.jobs import _rank
    ranked = _rank([{"match_score": 70, "remote": False, "id": 1}, {"match_score": 67, "remote": True, "id": 2},
                    {"match_score": None, "remote": True, "id": 3}])
    assert [r["id"] for r in ranked] == [2, 1, 3]

"""Live agent dashboard: run tracking service + /agent-runs API."""
import json
import sys
import uuid
from datetime import timedelta
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.db.database import SessionLocal
from backend.models.agent_runs import AgentRun
from backend.models.career_profile import CareerProfile, User
from backend.services import agent_runs as ar
from backend.services.auth_service import create_token

client = TestClient(app)

FAKE_NVIDIA_KEY = "nvapi-FAKEKEY1234567890abcdefXYZ"
FAKE_SERP_KEY = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"


def _user(prefix="runs"):
    db = SessionLocal()
    try:
        u = User(email=f"{prefix}-{uuid.uuid4().hex[:8]}@test.local", password_hash="x")
        db.add(u); db.commit(); db.refresh(u)
        db.add(CareerProfile(user_id=u.id, personal={}, professional={})); db.commit()
        return u.id, {"Authorization": f"Bearer {create_token(u.id)}"}
    finally:
        db.close()


def _row(run_id):
    db = SessionLocal()
    try:
        return db.get(AgentRun, run_id)
    finally:
        db.close()


def test_track_run_success_records_steps_tools_and_output():
    uid, _ = _user()
    with ar.track_run(uid, "job", "Search jobs: python", input_summary={"query": "python"}) as run:
        run.step("Search providers", 1, 2)
        with ar.tool_call("serpapi:google_jobs", "query=python") as t:
            t["summary"] = "3 jobs"
        run.step("Save jobs", 2, 2)
        run.set_output({"jobs_saved": 3})
    row = _row(run.id)
    assert row.status == "success" and row.finished_at is not None
    assert row.output_summary == {"jobs_saved": 3}
    assert row.input_summary == {"query": "python"}
    assert row.current_step is None
    assert len(row.tool_calls) == 1
    tc = row.tool_calls[0]
    assert tc["name"] == "serpapi:google_jobs" and tc["status"] == "success" and tc["summary"] == "3 jobs"
    assert isinstance(tc["duration_ms"], int) and tc["at"].endswith("Z")
    types = [e["type"] for e in row.events]
    assert types[0] == "started" and types[-1] == "finished" and types.count("step") == 2


def test_step_progress_is_visible_while_running():
    uid, _ = _user()
    with ar.track_run(uid, "cv", "Extract profile") as run:
        run.step("AI extraction", 2, 4)
        live = _row(run.id)
        assert live.status == "running"
        assert live.current_step == {"label": "AI extraction", "index": 2, "total": 4, "pct": 25}


def test_exception_marks_run_failed_and_is_reraised():
    uid, _ = _user()
    with pytest.raises(HTTPException):
        with ar.track_run(uid, "email", "Create Gmail draft") as run:
            with ar.tool_call("gmail:drafts.create"):
                raise HTTPException(status_code=409, detail="Gmail is not connected.")
    row = _row(run.id)
    assert row.status == "failed"
    assert row.error == "Gmail is not connected."
    assert row.tool_calls[0]["status"] == "failed"
    assert any(e["type"] == "tool_failed" for e in row.events)
    assert any(e["type"] == "failed" for e in row.events)
    assert row.logs[-1]["level"] == "error"


def test_explicit_fail_and_tool_status_without_exception():
    uid, _ = _user()
    with ar.track_run(uid, "job", "Search") as run:
        with ar.tool_call("apify:linkedin_jobs") as t:
            t["status"] = "failed"; t["summary"] = "wrong input"
        run.fail("No provider returned jobs")
    row = _row(run.id)
    assert row.status == "failed" and row.error == "No provider returned jobs"
    assert row.tool_calls[0]["status"] == "failed"


def test_secrets_are_never_stored():
    uid, _ = _user()
    with ar.track_run(uid, "job", f"Search with {FAKE_NVIDIA_KEY}",
                      input_summary={"api_key": "abc", "Authorization": "Bearer xyz", "q": f"key={FAKE_SERP_KEY}"}) as run:
        run.log("info", f"calling https://serpapi.com/search?api_key={FAKE_SERP_KEY}&q=x")
        run.log("info", f"header Authorization: Bearer {FAKE_NVIDIA_KEY}")
        with ar.tool_call("nvidia", f"token={FAKE_NVIDIA_KEY}"):
            pass
        run.set_output({"refresh_token": "1//secret", "note": FAKE_NVIDIA_KEY})
    row = _row(run.id)
    blob = json.dumps({c.name: getattr(row, c.name) for c in AgentRun.__table__.columns}, default=str)
    for secret in (FAKE_NVIDIA_KEY, FAKE_SERP_KEY, "Bearer xyz", "1//secret"):
        assert secret not in blob, secret
    assert row.input_summary["api_key"] == "[redacted]"
    assert row.output_summary["refresh_token"] == "[redacted]"


def test_long_values_are_truncated_and_documents_not_stored():
    uid, _ = _user()
    with ar.track_run(uid, "cv", "Extract", input_summary={"text": "x" * 5000, "file": b"%PDF" * 100}) as run:
        pass
    row = _row(run.id)
    assert len(row.input_summary["text"]) < 400
    assert row.input_summary["file"] == "<400 bytes>"


def test_helpers_are_noops_without_active_run():
    with ar.tool_call("nvidia:x", "y") as t:
        t["summary"] = "fine"
    ar.run_log("info", "nothing"); ar.run_warn("nothing"); ar.run_step("x", 1, 1)
    assert ar.current_run() is None


def test_unknown_agent_rejected():
    with pytest.raises(ValueError):
        with ar.track_run(1, "chat", "x"):
            pass


def test_snapshot_shape_matches_frontend_contract():
    uid, headers = _user()
    with ar.track_run(uid, "cv", "Extract career profile") as run:
        run.step("AI extraction", 1, 1)
        with ar.tool_call("nvidia:openai/gpt-oss-20b"):
            pass
    r = client.get("/agent-runs/snapshot?range=1h", headers=headers)
    assert r.status_code == 200
    snap = r.json()
    assert set(snap) >= {"generated_at", "agents", "runs", "timeline"}
    assert [a["agent"] for a in snap["agents"]] == ["cv", "job", "email"]
    for a in snap["agents"]:
        assert set(a) >= {"agent", "state", "current_task", "started_at", "last_activity_at"}
        assert a["state"] in ("running", "idle", "waiting", "error")
    assert snap["agents"][0]["state"] == "idle" and snap["agents"][0]["current_task"] == "Extract career profile"
    run_json = snap["runs"][0]
    for key in ("id", "agent", "task", "status", "started_at", "finished_at", "correlation_id",
                "retry_count", "current_step", "input", "output", "tool_calls", "logs", "events"):
        assert key in run_json, key
    assert run_json["status"] == "success" and run_json["started_at"].endswith("Z")
    assert run_json["tool_calls"][0]["name"] == "nvidia:openai/gpt-oss-20b"
    assert {t["title"] for t in snap["timeline"]} >= {"Started", "Completed"}
    for t in snap["timeline"]:
        assert set(t) >= {"id", "at", "agent", "title", "detail", "status"}


def test_running_and_failed_agent_states():
    uid, headers = _user()
    with pytest.raises(RuntimeError):
        with ar.track_run(uid, "email", "Prepare application"):
            raise RuntimeError("boom")
    with ar.track_run(uid, "job", "Search jobs: data") as run:
        snap = client.get("/agent-runs/snapshot?range=24h", headers=headers).json()
        states = {a["agent"]: a for a in snap["agents"]}
        assert states["job"]["state"] == "running" and states["job"]["current_task"] == "Search jobs: data"
        assert states["email"]["state"] == "error"
        running = next(r for r in snap["runs"] if r["id"] == run.id)
        assert running["status"] == "running" and running["finished_at"] is None


def test_snapshot_is_scoped_to_the_current_user():
    uid_a, headers_a = _user("a")
    _, headers_b = _user("b")
    with ar.track_run(uid_a, "cv", "Private run of A") as run:
        pass
    snap_b = client.get("/agent-runs/snapshot?range=7d", headers=headers_b).json()
    assert all(r["id"] != run.id for r in snap_b["runs"])
    assert client.get(f"/agent-runs/{run.id}", headers=headers_b).status_code == 404
    assert client.get(f"/agent-runs/{run.id}", headers=headers_a).json()["task"] == "Private run of A"
    assert client.get("/agent-runs/snapshot").status_code == 401


def test_invalid_range_rejected():
    _, headers = _user()
    assert client.get("/agent-runs/snapshot?range=1y", headers=headers).status_code == 400


def test_stale_running_runs_are_timed_out():
    uid, headers = _user()
    db = SessionLocal()
    try:
        old = AgentRun(id=str(uuid.uuid4()), user_id=uid, agent="job", task="Stuck search", status="running",
                       started_at=ar.utcnow() - timedelta(minutes=11), tool_calls=[], logs=[], events=[])
        db.add(old); db.commit(); stale_id = old.id
    finally:
        db.close()
    snap = client.get("/agent-runs/snapshot?range=1h", headers=headers).json()
    run_json = next(r for r in snap["runs"] if r["id"] == stale_id)
    assert run_json["status"] == "failed" and "Timed out" in run_json["error"]
    assert _row(stale_id).status == "failed"


def test_nvidia_calls_are_recorded_as_tool_calls_with_fallback_warning(monkeypatch):
    from backend.services import nvidia_llm
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_NVIDIA_KEY)
    monkeypatch.setenv("NVIDIA_MODEL", "primary/model")
    monkeypatch.setenv("NVIDIA_FALLBACK_MODEL", "fallback/model")
    calls = []

    def fake_complete(model, *a, **k):
        calls.append(model)
        if model == "primary/model":
            raise nvidia_llm.LLMUnavailableError("NVIDIA model primary/model timed out after 45s")
        return '{"ok": true}'

    uid, _ = _user()
    with mock.patch.object(nvidia_llm, "_complete", side_effect=fake_complete):
        with ar.track_run(uid, "cv", "Tailor resume") as run:
            assert nvidia_llm.call_nvidia_llm("hi") == '{"ok": true}'
    row = _row(run.id)
    assert [t["name"] for t in row.tool_calls] == ["nvidia:primary/model", "nvidia:fallback/model"]
    assert [t["status"] for t in row.tool_calls] == ["failed", "success"]
    assert any("trying fallback model" in l["message"] for l in row.logs)
    assert FAKE_NVIDIA_KEY not in json.dumps(row.tool_calls + row.logs)


def test_profile_extract_endpoint_is_tracked_and_reports_fallback():
    uid, headers = _user()
    from backend.services.nvidia_llm import LLMUnavailableError
    with mock.patch("backend.ai_agents.profile_agent.call_nvidia_llm",
                    side_effect=LLMUnavailableError("NVIDIA model x timed out after 45s")):
        r = client.post("/profiles/me/extract", headers=headers,
                        json={"text": "Jordan Avery\njordan@example.com\nSkills: Python, SQL", "auto_save": True})
    assert r.status_code == 200
    snap = client.get("/agent-runs/snapshot?range=1h", headers=headers).json()
    cv_run = next(r for r in snap["runs"] if r["agent"] == "cv")
    assert cv_run["task"] == "Extract career profile from text"
    assert cv_run["status"] == "success"
    steps = [e["detail"] for e in cv_run["events"] if e["type"] == "step"]
    assert steps == ["Step 1/2: AI extraction", "Step 2/2: Save profile"]
    assert any("pattern-matching fallback" in l["message"] for l in cv_run["logs"])
    assert cv_run["input"]["text_chars"] > 0 and "jordan@example.com" not in json.dumps(cv_run["input"])
    assert any(t["title"] == "Warning" for t in snap["timeline"])

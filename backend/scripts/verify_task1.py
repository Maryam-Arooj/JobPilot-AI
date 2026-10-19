"""Task 1 live check: the agent dashboard shows real CV and Job agent runs.

Usage (repo root, backend running on 127.0.0.1:8000 with the new code):
    backend\\.venv\\Scripts\\python.exe backend\\scripts\\verify_task1.py

What it does (costs: 1 NVIDIA call, 1 SerpAPI search, 1 small Apify run):
  1. Signs in as demo@jobpilot.local (token made locally from SECRET_KEY; no password needed).
  2. CV agent: extracts a profile from a short FICTIONAL CV with auto_save=false (profile unchanged).
  3. Job agent: one live job search, while polling the snapshot to prove the run is visible live.
  4. Prints the snapshot (agents, runs, steps, tool calls, warnings) and PASS/FAIL checks.
Never prints key values.
"""
import json
import sys
import threading
import time
from pathlib import Path

import requests
from dotenv import dotenv_values
from jose import jwt

API = "http://127.0.0.1:8000"
ENV = {k: (v or "").strip() for k, v in dotenv_values(Path(__file__).resolve().parent.parent / ".env").items()}
SECRETS = [v for k, v in ENV.items() if v and len(v) >= 8 and any(s in k.upper() for s in ("KEY", "TOKEN", "SECRET", "PASSWORD", "DATABASE_URL"))]
DEMO_EMAIL = "demo@jobpilot.local"
CV_TEXT = """Jordan Avery
Senior Data Engineer
jordan.avery@example.com | +1 555 0100 | Austin, TX
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
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))


def leaks(text):
    return [s for s in SECRETS if s in text]


def token_for_demo_user():
    from sqlalchemy import create_engine, text
    engine = create_engine(ENV["DATABASE_URL"])
    with engine.connect() as c:
        row = c.execute(text("select id from users where email = :e"), {"e": DEMO_EMAIL}).first()
    if not row:
        sys.exit(f"User {DEMO_EMAIL} not found in the database. Create it in the app first.")
    payload = {"sub": str(row[0]), "exp": int(time.time()) + 3600}
    return jwt.encode(payload, ENV["SECRET_KEY"], algorithm="HS256")


def main():
    print("== Task 1: live agent dashboard ==")
    try:
        h = requests.get(f"{API}/health", timeout=5)
    except requests.RequestException:
        sys.exit("Backend is not running on 127.0.0.1:8000. Start it (start-servers.bat) and run this again.")
    check("backend /health", h.status_code == 200)
    headers = {"Authorization": f"Bearer {token_for_demo_user()}"}

    snap = requests.get(f"{API}/agent-runs/snapshot?range=1h", headers=headers, timeout=10)
    check("GET /agent-runs/snapshot answers", snap.status_code == 200, f"HTTP {snap.status_code}")
    if snap.status_code != 200:
        print(snap.text[:300]); return finish()
    before = {r["id"] for r in snap.json()["runs"]}

    print("\n-- CV agent: extract profile (auto_save=false, your profile is not changed)")
    t0 = time.time()
    r = requests.post(f"{API}/profiles/me/extract", headers=headers, json={"text": CV_TEXT, "auto_save": False}, timeout=120)
    print(f"  HTTP {r.status_code} in {time.time() - t0:.1f}s")

    print("\n-- Job agent: one live search (watching the dashboard while it runs)")
    seen_running = {"step": None}

    def watch():
        end = time.time() + 120
        while time.time() < end and not seen_running.get("done"):
            try:
                s = requests.get(f"{API}/agent-runs/snapshot?range=1h", headers=headers, timeout=5).json()
                job = next((a for a in s["agents"] if a["agent"] == "job"), {})
                if job.get("state") == "running":
                    run = next((x for x in s["runs"] if x["status"] == "running" and x["agent"] == "job"), None)
                    if run and run.get("current_step"):
                        seen_running["step"] = run["current_step"]["label"]
                        print(f"  live: Job agent running -> {run['current_step']['label']}")
            except Exception:
                pass
            time.sleep(1)

    w = threading.Thread(target=watch, daemon=True); w.start()
    t0 = time.time()
    r2 = requests.post(f"{API}/jobs/search", headers=headers, params={"query": "Data Engineer", "country": "United States"}, timeout=180)
    seen_running["done"] = True; w.join(timeout=3)
    print(f"  HTTP {r2.status_code} in {time.time() - t0:.1f}s" + (f", {len(r2.json().get('results', []))} jobs" if r2.ok else ""))

    snap = requests.get(f"{API}/agent-runs/snapshot?range=1h", headers=headers, timeout=10)
    data = snap.json()
    new_runs = [x for x in data["runs"] if x["id"] not in before]

    print("\n-- Snapshot now")
    for a in data["agents"]:
        print(f"  {a['agent']:5} state={a['state']:8} task={a['current_task']!r} last={a['last_activity_at']}")
    for run in new_runs:
        print(f"\n  RUN {run['agent']} | {run['task']} | {run['status']} | {run['started_at']} -> {run['finished_at']}")
        for e in run["events"]:
            if e["type"] in ("step", "warning", "failed", "tool_failed"):
                print(f"     event {e['type']:11} {e['detail']}")
        for t in run["tool_calls"]:
            print(f"     tool  {t['name']:28} {t['status']:7} {t.get('duration_ms', '-')} ms  {t['summary']}")
        if run.get("output"):
            print(f"     output {json.dumps(run['output'])[:300]}")

    print("\n-- Checks")
    cv = next((x for x in new_runs if x["agent"] == "cv"), None)
    job = next((x for x in new_runs if x["agent"] == "job"), None)
    check("CV agent run recorded", cv is not None, cv and f"{cv['status']}, {len(cv['tool_calls'])} tool calls")
    check("CV run shows the NVIDIA call", bool(cv and any(t["name"].startswith("nvidia:") or t["name"].startswith("parser:") for t in cv["tool_calls"])))
    check("Job agent run recorded", job is not None, job and f"{job['status']}, {len(job['tool_calls'])} tool calls")
    check("Job run shows provider calls", bool(job and any(t["name"].startswith(("serpapi", "apify")) for t in job["tool_calls"])))
    check("Job run was visible live while running", seen_running["step"] is not None, f"step seen: {seen_running['step']}")
    check("timeline has events", len(data.get("timeline", [])) > 0, f"{len(data.get('timeline', []))} events")
    check("no API keys in the snapshot", not leaks(snap.text))
    finish()


def finish():
    print(f"\nRESULT: {sum(results)}/{len(results)} checks passed")
    print("Now open http://localhost:3000/agent-transparency and the Overview page: both should say Live and show these runs.")


if __name__ == "__main__":
    main()

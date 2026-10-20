"""Task 3 live check: Job Agent with real SerpAPI (Google Jobs) + Apify (LinkedIn) and honest matching.

Usage (repo root, backend running):
    backend\\.venv\\Scripts\\python.exe backend\\scripts\\verify_task3.py                 # demo account
    backend\\.venv\\Scripts\\python.exe backend\\scripts\\verify_task3.py you@gmail.com   # your account (your saved CV)

Costs: 1-2 SerpAPI searches, 1 small Apify run, 1 AI call. Never prints keys.
"""
import sys
import time
from pathlib import Path

import requests
from dotenv import dotenv_values
from jose import jwt

API = "http://127.0.0.1:8000"
ENV = {k: (v or "").strip() for k, v in dotenv_values(Path(__file__).resolve().parent.parent / ".env").items()}
EMAIL = sys.argv[1] if len(sys.argv) > 1 else "demo@jobpilot.local"
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))


def token():
    from sqlalchemy import create_engine, text
    with create_engine(ENV["DATABASE_URL"]).connect() as c:
        row = c.execute(text("select id from users where email = :e"), {"e": EMAIL}).first()
    if not row:
        sys.exit(f"{EMAIL} not found in the database.")
    return jwt.encode({"sub": str(row[0]), "exp": int(time.time()) + 3600}, ENV["SECRET_KEY"], algorithm="HS256")


def main():
    print(f"== Task 3: Job Agent ({EMAIL}) ==")
    try:
        requests.get(f"{API}/health", timeout=5)
    except requests.RequestException:
        sys.exit("Backend is not running on 127.0.0.1:8000.")
    h = {"Authorization": f"Bearer {token()}"}

    print("\n-- 1. Find jobs for the saved CV (/jobs/from-cv)")
    t0 = time.time()
    r = requests.post(f"{API}/jobs/from-cv", headers=h, json={}, timeout=180)
    dt = time.time() - t0
    print(f"  HTTP {r.status_code} in {dt:.1f}s")
    if r.status_code != 200:
        print("  " + r.text[:400]); return finish()
    body = r.json()
    print(f"  search: role={body['query']!r} location={body['location']!r}")
    for name, st in body["provider_status"].items():
        print(f"  provider {name:22} " + (f"OK, {st['jobs']} jobs" if st.get("ok") else f"FAILED: {st.get('error')}"))
    jobs = body["results"]
    print(f"\n  {'score':>5}  {'job':55} matched / missing")
    for j in jobs[:12]:
        score = "-" if j["match_score"] is None else f"{j['match_score']}%"
        print(f"  {score:>5}  {(j['title'] + ' @ ' + j['company'])[:55]:55} {', '.join(j['matched_skills'][:4])} / {', '.join(j['missing_skills'][:3])}")
    check("live jobs returned", len(jobs) > 0, f"{len(jobs)} jobs")
    check("Google Jobs (SerpAPI) answered", body["provider_status"].get("serpapi:google_jobs", {}).get("ok"))
    check("LinkedIn (Apify) answered", body["provider_status"].get("apify:linkedin_jobs", {}).get("ok"),
          "optional: results still come from Google Jobs if this fails")
    scored = [j for j in jobs if j["match_score"] is not None]
    check("ranked by match score", [j["match_score"] for j in scored] == sorted((j["match_score"] for j in scored), reverse=True))
    check("no invented scores (jobs without skills show no score)", all(j["match_score"] is None or j["matched_skills"] or j["missing_skills"] for j in jobs))

    if jobs:
        top = scored[0] if scored else jobs[0]
        print(f"\n-- 2. AI match for: {top['title']} @ {top['company']}")
        t0 = time.time()
        m = requests.post(f"{API}/jobs/{top['id']}/match", headers=h, timeout=120)
        print(f"  HTTP {m.status_code} in {time.time() - t0:.1f}s")
        if m.ok:
            mb = m.json()
            print(f"  method={mb['method']} score={mb['match_score']} alignment={mb['overall_alignment']}")
            print(f"  matched: {', '.join(mb['matched_requirements'][:8])}")
            print(f"  gaps:    {', '.join(mb['gaps'][:8])}")
            check("AI match answered with evidence", mb["method"] == "ai" and mb["evidence"] is not None, mb["method"])

    snap = requests.get(f"{API}/agent-runs/snapshot?range=1h", headers=h, timeout=10).json()
    print("\n-- Dashboard (latest Job agent runs)")
    for run in [x for x in snap["runs"] if x["agent"] == "job"][:2]:
        tools = ", ".join(f"{t['name']} {t['status']} {t.get('duration_ms', '-')}ms" for t in run["tool_calls"])
        print(f"  {run['task']} | {run['status']} | {tools}")
    finish()


def finish():
    print(f"\nRESULT: {sum(results)}/{len(results)} checks passed")


if __name__ == "__main__":
    main()

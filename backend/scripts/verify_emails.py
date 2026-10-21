"""Live check of the recipient-email search for your newest saved jobs.

Usage (repo root, backend running):
    backend\\.venv\\Scripts\\python.exe backend\\scripts\\verify_emails.py maryamarooj128x@gmail.com [how_many=8]

Uses SerpAPI, Firecrawl and Apify credits (results are saved, so a second run is free). Never prints keys.
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
N = int(sys.argv[2]) if len(sys.argv) > 2 else 8


def main():
    from sqlalchemy import create_engine, text
    try:
        requests.get(f"{API}/health", timeout=5)
    except Exception:
        sys.exit("Backend is not running on 127.0.0.1:8000. Start it first.")
    with create_engine(ENV["DATABASE_URL"]).connect() as c:
        user = c.execute(text("select id from users where email = :e"), {"e": EMAIL}).first()
    if not user:
        sys.exit(f"{EMAIL} is not a JobPilot login.")
    tok = jwt.encode({"sub": str(user[0]), "exp": int(time.time()) + 3600}, ENV["SECRET_KEY"], algorithm="HS256")
    h = {"Authorization": f"Bearer {tok}"}
    jobs = requests.get(f"{API}/jobs/", headers=h, timeout=30).json()[:N]
    if not jobs:
        sys.exit("No saved jobs. Run 'Find jobs for my CV' in the app first.")
    print(f"== Recipient email search for {len(jobs)} jobs ==")
    t0 = time.time()
    task = requests.post(f"{API}/jobs/find-emails", json={"job_ids": [j["id"] for j in jobs]}, headers=h, timeout=30).json()
    while True:
        time.sleep(3)
        t = requests.get(f"{API}/jobs/find-emails/{task['task_id']}", headers=h, timeout=30).json()
        print(f"  ... {t['done']}/{t['total']} companies ({time.time() - t0:.0f}s)")
        if t["status"] != "running":
            break
    found = t.get("found") or {}
    hits = 0
    for j in jobs:
        emails = found.get(str(j["id"])) or j.get("recipient_emails") or []
        hits += bool(emails)
        print(f"  [{'EMAIL' if emails else '  -  '}] {j['title'][:45]:45} | {j['company'][:28]:28} | {', '.join(emails) or 'none published'}")
    print(f"\n{hits}/{len(jobs)} jobs have a real recruiter email (status: {t['status']}"
          f"{', error: ' + t['error'] if t.get('error') else ''}). Total time {time.time() - t0:.0f}s.")
    print("Open Agent Transparency to see every search step.")


if __name__ == "__main__":
    main()

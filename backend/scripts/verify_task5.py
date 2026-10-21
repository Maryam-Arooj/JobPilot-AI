"""Task 5 live check: the one-click "Apply with AI" pipeline.

Usage (repo root, backend running):
    backend\\.venv\\Scripts\\python.exe backend\\scripts\\verify_task5.py maryamarooj128x@gmail.com [Pakistan|Remote]

Costs: 1-2 job searches, recruiter-email search for up to 10 jobs, 1 company research, 1 AI email.
It never creates or sends a Gmail draft. Never prints keys.
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
WHERE = sys.argv[2] if len(sys.argv) > 2 else "Pakistan"


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
    body = {"mode": "remote"} if WHERE.lower() == "remote" else {"location": WHERE, "mode": "location"}
    pid = requests.post(f"{API}/pipeline/apply", json=body, headers=h, timeout=30).json()["pipeline_id"]
    print(f"== Apply with AI ({WHERE}) ==")
    shown = {}
    while True:
        time.sleep(2)
        s = requests.get(f"{API}/pipeline/{pid}", headers=h, timeout=30).json()
        for i, st in enumerate(s["steps"]):
            key = (st["status"], st["detail"])
            if shown.get(i) != key and st["status"] != "pending":
                shown[i] = key
                print(f"  [{st['status'].upper():7}] {st['name']}" + (f" - {st['detail']}" if st["detail"] else ""))
        if s["status"] != "running":
            break
    print(f"\nResult: {s['status']} after {s['elapsed']}s")
    if s["status"] == "ready":
        print(f"  Open http://localhost:3000/applications?id={s['application_id']} to review and approve the draft.")
    else:
        print(f"  {s['error']}")


if __name__ == "__main__":
    main()

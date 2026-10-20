"""Task 4 live check: Email Agent with real company research (SerpAPI + Firecrawl + AI) and a fact-checked email.

Usage (repo root, backend running):
    backend\\.venv\\Scripts\\python.exe backend\\scripts\\verify_task4.py you@gmail.com
    backend\\.venv\\Scripts\\python.exe backend\\scripts\\verify_task4.py you@gmail.com draft hr@realcompany.com

It uses your newest saved job. Costs: 1 SerpAPI search, 1-2 Firecrawl pages, 2 AI calls.
A Gmail draft is created ONLY when you add: draft <recipient>. Nothing is ever sent. Never prints keys.
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
DRAFT_TO = sys.argv[3] if len(sys.argv) > 3 and sys.argv[2] == "draft" else None
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))


def main():
    from sqlalchemy import create_engine, text
    print(f"== Task 4: Email Agent ({EMAIL}) ==")
    try:
        requests.get(f"{API}/health", timeout=5)
    except Exception:
        sys.exit("Backend is not running on 127.0.0.1:8000. Start it first.")
    with create_engine(ENV["DATABASE_URL"]).connect() as c:
        user = c.execute(text("select id from users where email = :e"), {"e": EMAIL}).first()
        if not user:
            sys.exit(f"{EMAIL} not found in the database.")
        job = c.execute(text("select j.id, j.title, j.company from jobs j order by j.id desc limit 1")).first()
    if not job:
        sys.exit("No saved jobs yet. Search jobs in the app first (Task 3).")
    tok = jwt.encode({"sub": str(user[0]), "exp": int(time.time()) + 3600}, ENV["SECRET_KEY"], algorithm="HS256")
    h = {"Authorization": f"Bearer {tok}"}
    print(f"  job: {job[1]} at {job[2]} (#{job[0]})")

    t = time.time()
    r = requests.post(f"{API}/applications/prepare", json={"job_id": job[0]}, headers=h, timeout=240)
    check("prepare application", r.status_code == 200, f"HTTP {r.status_code} in {time.time() - t:.0f}s")
    if r.status_code != 200:
        print("   ", r.text[:300]); return
    app = r.json()
    res = app["company"]["research"] or {}
    print(f"  company research: status={res.get('status')} website={res.get('official_website') or '-'}")
    if res.get("message"):
        print(f"    {res['message']}")
    for c in (res.get("claims") or [])[:5]:
        print(f"    - [{c['fact_type']}] {c['claim_text'][:110]}")
    check("research is honest", res.get("status") in ("found", "not_found", "unavailable"),
          "facts come from the company website" if res.get("status") == "found" else "no invented company facts")
    check("no guessed website", res.get("status") == "found" or not app["company"]["official_website"]
          or res.get("status") == "unavailable")

    r = requests.post(f"{API}/applications/{app['id']}/generate-email", json={"tone": "Technical"}, headers=h, timeout=120)
    check("generate email", r.status_code == 200, f"HTTP {r.status_code}")
    if r.status_code == 200:
        e = r.json()
        check("written by AI", e.get("method") == "ai", e.get("method"))
        print(f"  subject: {e['subject']}")
        print("  " + e["body"].replace("\n", "\n  "))
        if e.get("removed_claims"):
            print(f"  fact checker removed {len(e['removed_claims'])}:")
            for x in e["removed_claims"]:
                print(f"    - {x[:140]}")

    g = requests.get(f"{API}/gmail/status", headers=h, timeout=10).json()
    check("Gmail connected", g.get("connected"), g.get("email") or "connected, address unknown - reconnect once")
    if DRAFT_TO and g.get("connected") and r.status_code == 200:
        d = requests.post(f"{API}/applications/{app['id']}/gmail-draft", headers=h, timeout=60, json={
            "recipient": DRAFT_TO, "subject": e["subject"], "body": e["body"], "user_confirmed": True,
            "include_attachment": True, "attachment_format": "pdf"})
        check("Gmail draft created (not sent)", d.status_code == 200, d.json().get("message") if d.ok else d.text[:200])
    print(f"\n{sum(results)}/{len(results)} checks passed. Open Agent Transparency to see these Email runs live.")


if __name__ == "__main__":
    main()

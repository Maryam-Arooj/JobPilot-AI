"""JobPilot AI - full end-to-end live check (CV Agent, Job Agent, Email Agent, pipeline, Gmail, dashboard).

Usage (repo root, backend running):
    backend\\.venv\\Scripts\\python.exe backend\\scripts\\e2e_check.py you@login.email [Pakistan|Remote] [path\\to\\cv.pdf] [draft:recipient@x.com]

Every step prints PASS / FAIL / WARN with the reason. Nothing is sent: a Gmail draft is created only with "draft:<address>".
Costs: a few AI calls, 1-2 job searches, recruiter-email search for up to 10 jobs. Never prints keys.
"""
import sys
import time
from pathlib import Path

import requests
from dotenv import dotenv_values
from jose import jwt

API = "http://127.0.0.1:8000"
ENV = {k: (v or "").strip() for k, v in dotenv_values(Path(__file__).resolve().parent.parent / ".env").items()}
ARGS = sys.argv[1:]
EMAIL = ARGS[0] if ARGS else "demo@jobpilot.local"
WHERE = next((a for a in ARGS[1:] if a.lower() in ("pakistan", "remote") or (a[:1].isupper() and not a.endswith((".pdf", ".docx", ".txt")) and ":" not in a)), "Pakistan")
CV = next((a for a in ARGS[1:] if a.lower().endswith((".pdf", ".docx", ".txt"))), None)
DRAFT_TO = next((a.split(":", 1)[1] for a in ARGS[1:] if a.startswith("draft:")), None)
rows = []


def report(name, status, detail=""):
    rows.append((name, status))
    print(f"  [{status:4}] {name}" + (f" - {detail}" if detail else ""))


def main():
    from sqlalchemy import create_engine, text
    print(f"== JobPilot AI end-to-end check ({EMAIL}, {WHERE}) ==\n")
    # 0. backend + database + login
    try:
        h0 = requests.get(f"{API}/health", timeout=5)
        report("Backend running", "PASS" if h0.ok else "FAIL", f"HTTP {h0.status_code}")
    except Exception:
        report("Backend running", "FAIL", "not reachable on 127.0.0.1:8000 - start the backend first")
        return finish()
    try:
        with create_engine(ENV["DATABASE_URL"]).connect() as c:
            user = c.execute(text("select id from users where email = :e"), {"e": EMAIL}).first()
        report("Database", "PASS")
    except Exception as e:
        report("Database", "FAIL", str(e).splitlines()[0][:120]); return finish()
    if not user:
        report("Login account", "FAIL", f"{EMAIL} is not a JobPilot login"); return finish()
    h = {"Authorization": f"Bearer {jwt.encode({'sub': str(user[0]), 'exp': int(time.time()) + 3600}, ENV['SECRET_KEY'], algorithm='HS256')}"}
    report("Login account", "PASS")

    # 1. CV Agent
    print("\n-- CV Agent")
    if CV:
        p = Path(CV)
        if not p.exists():
            report("CV file", "FAIL", f"{CV} not found")
        else:
            t = time.time()
            r = requests.post(f"{API}/documents/parse", headers=h, timeout=60, files={"file": (p.name, p.read_bytes())})
            if r.ok:
                n = len(r.json().get("facts") or [])
                report("Read uploaded CV (quick read)", "PASS" if n else "FAIL", f"{n} facts in {time.time() - t:.1f}s")
            else:
                report("Read uploaded CV", "FAIL", f"HTTP {r.status_code} {r.text[:150]}")
    prof = requests.get(f"{API}/profiles/me", headers=h, timeout=20)
    pd = prof.json() if prof.ok else {}
    skills = (pd.get("professional") or {}).get("skills") or []
    name = (pd.get("personal") or {}).get("name") or (pd.get("personal") or {}).get("full_name")
    report("Saved CV profile", "PASS" if name and skills else "FAIL",
           f"name: {name or 'missing'}, {len(skills)} skills" + ("" if name and skills else " - upload and sync your CV on the Confirm page"))
    bad = [s for s in skills if isinstance(s, str) and (s.startswith("[") or "," in s)]
    report("Skills stored as a clean list", "PASS" if not bad else "FAIL", f"{len(bad)} broken entries" if bad else "")

    # 2. Job Agent
    print("\n-- Job Agent")
    body = {"mode": "remote"} if WHERE.lower() == "remote" else {"location": WHERE, "mode": "location"}
    t = time.time()
    r = requests.post(f"{API}/jobs/from-cv", json=body, headers=h, timeout=180)
    jobs = r.json().get("results", []) if r.ok else []
    report("Live jobs for your CV", "PASS" if jobs else "FAIL",
           f"{len(jobs)} jobs in {time.time() - t:.0f}s ({r.json().get('searched') if r.ok else r.text[:120]})")
    if r.ok:
        for prov, st in (r.json().get("provider_status") or {}).items():
            ok = isinstance(st, dict) and st.get("ok")
            report(f"  provider {prov}", "PASS" if ok else "WARN",
                   f"{st.get('jobs')} jobs" if ok else str((st or {}).get("error") if isinstance(st, dict) else st)[:120])
    scored = [j for j in jobs if j.get("match_score") is not None]
    matched = [j for j in scored if j.get("matched_skills")]
    report("Honest match scores", "PASS" if matched else ("WARN" if jobs else "FAIL"),
           f"{len(scored)} scored, {len(matched)} with matched skills; top: " +
           (f"{jobs[0]['title']} @ {jobs[0]['company']} ({jobs[0].get('match_score')}%)" if jobs else "-"))
    if WHERE.lower() == "pakistan" and jobs:
        pk = [j for j in jobs if j.get("country") == "Pakistan"]
        report("Pakistan jobs with city/province", "PASS" if pk else "WARN",
               f"{len(pk)} in Pakistan, e.g. {pk[0]['location']}" if pk else "none of the results are in Pakistan")

    # 3. Pipeline (Email Agent finds recipients, picks best job, writes email)
    print("\n-- Apply with AI (all three agents)")
    t = time.time()
    pid = requests.post(f"{API}/pipeline/apply", json={**body, "require_email": True, "max_jobs": 10}, headers=h, timeout=30).json()["pipeline_id"]
    while True:
        time.sleep(3)
        s = requests.get(f"{API}/pipeline/{pid}", headers=h, timeout=30).json()
        if s["status"] != "running":
            break
    for st in s["steps"]:
        report(f"  {st['name']}", {"done": "PASS", "waiting": "PASS", "failed": "FAIL"}.get(st["status"], "WARN"), st["detail"][:140])
    report("Pipeline", "PASS" if s["status"] == "ready" else "FAIL", f"{s['status']} in {time.time() - t:.0f}s {s.get('error') or ''}")
    if s["status"] != "ready":
        return finish(h)

    # 4. Application: research, email, recipient, CV
    print("\n-- Email Agent (application)")
    app = requests.get(f"{API}/applications/{s['application_id']}", headers=h, timeout=30).json()
    res = (app.get("company") or {}).get("research") or {}
    report("Company research", "PASS" if res.get("status") == "found" else "WARN",
           f"{res.get('status')} - {res.get('official_website') or res.get('message') or ''}")
    ev = app.get("email_version") or {}
    body_txt = ev.get("body") or ""
    report("Application email written", "PASS" if len(body_txt) > 200 else "FAIL", f"{len(body_txt)} characters, subject: {ev.get('subject')}")
    report("One greeting, one sign-off", "PASS" if body_txt.count("Dear ") <= 1 and body_txt.lower().count("regards") + body_txt.lower().count("sincerely") <= 1 else "FAIL")
    report("Recipient email (real)", "PASS" if s.get("recipient") else "WARN", s.get("recipient") or "none published")
    cv = app.get("cv_attachment") or {}
    report("CV will be attached", "PASS" if cv.get("source") else "FAIL", cv.get("label") or "no CV found")

    # 5. Gmail
    print("\n-- Gmail")
    g = requests.get(f"{API}/gmail/status", headers=h, timeout=15).json()
    report("Gmail connected", "PASS" if g.get("connected") else "FAIL", g.get("email") or "connect Gmail on the Applications page")
    if DRAFT_TO and g.get("connected"):
        d = requests.post(f"{API}/applications/{app['id']}/gmail-draft", headers=h, timeout=90, json={
            "recipient": DRAFT_TO, "subject": ev.get("subject"), "body": body_txt, "user_confirmed": True,
            "include_attachment": True, "attachment_format": "pdf"})
        report("Gmail draft with CV", "PASS" if d.ok and d.json().get("has_attachment") else "FAIL",
               d.json().get("attachment_name") if d.ok else d.json().get("detail", d.text)[:200])
    elif not DRAFT_TO:
        report("Gmail draft", "SKIP", "add draft:your@gmail.com to create one test draft")
    return finish(h)


def finish(h=None):
    if h:
        print("\n-- Live dashboard")
        snap = requests.get(f"{API}/agent-runs/snapshot?range=1h", headers=h, timeout=20)
        if snap.ok:
            runs = snap.json().get("runs") or []
            by = {a: sum(1 for r in runs if r.get("agent") == a) for a in ("cv", "job", "email")}
            failed = sum(1 for r in runs if r.get("status") == "failed")
            report("Agent Transparency has the runs", "PASS" if runs else "FAIL",
                   f"last hour: CV {by['cv']}, Job {by['job']}, Email {by['email']} runs ({failed} failed)")
        else:
            report("Agent Transparency", "FAIL", f"HTTP {snap.status_code}")
    p = sum(1 for _, s in rows if s == "PASS")
    f = [n for n, s in rows if s == "FAIL"]
    w = [n for n, s in rows if s == "WARN"]
    print(f"\n== {p} passed, {len(f)} failed, {len(w)} warnings ==")
    for n in f:
        print(f"  FAIL: {n}")
    print("Paste this whole output to Claude if anything failed.")


if __name__ == "__main__":
    main()

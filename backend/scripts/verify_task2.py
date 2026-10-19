"""Task 2 live check: the CV Agent extracts only what is in the CV, and facts need confirmation.

Usage (repo root, backend running on 127.0.0.1:8000 with the new code):
    backend\\.venv\\Scripts\\python.exe backend\\scripts\\verify_task2.py

Costs: ~3 NVIDIA calls. Uses the demo account demo@jobpilot.local (fictional "Jordan Avery"):
its profile is re-extracted from the same fictional CV below, then the facts are confirmed.
Never prints key values.
"""
import io
import json
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import dotenv_values
from jose import jwt

API = "http://127.0.0.1:8000"
ENV = {k: (v or "").strip() for k, v in dotenv_values(Path(__file__).resolve().parent.parent / ".env").items()}
DEMO_EMAIL = "demo@jobpilot.local"
CV_LINES = [
    "Jordan Avery",
    "Senior Data Engineer",
    "jordan.avery@example.com | +1 555 0100 2233 | Austin, TX | linkedin.com/in/jordan-avery-demo",
    "SUMMARY",
    "Data engineer with 7 years of experience building batch and streaming data pipelines for analytics teams.",
    "EXPERIENCE",
    "Senior Data Engineer, Northwind Analytics, Austin, TX (2021 - Present)",
    "Built Airflow and Spark pipelines on AWS that cut warehouse load time by 40%.",
    "Introduced dbt tests and data quality checks for 120 tables.",
    "Data Engineer, Contoso Retail, Dallas, TX (2018 - 2021)",
    "Maintained PostgreSQL and Python ETL jobs for daily sales reporting.",
    "EDUCATION",
    "BS Computer Science, University of Texas at Austin, 2018",
    "PROJECTS",
    "Open Lineage Explorer - a small tool that visualises dbt lineage graphs.",
    "CERTIFICATIONS",
    "AWS Certified Data Engineer - Associate",
    "SKILLS",
    "Python, SQL, Airflow, Spark, dbt, AWS, PostgreSQL, Docker",
]
CV_TEXT = "\n".join(CV_LINES)
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))


def norm(s):
    s = str(s).lower().replace("–", "-").replace("—", "-")
    s = re.sub(r"https?://|www\.", "", s)
    return re.sub(r"[^a-z0-9+#]", "", s)


def in_cv(value):
    v = norm(value)
    return bool(v) and v in norm(CV_TEXT)


def docx_bytes():
    import docx
    d = docx.Document()
    for line in CV_LINES:
        d.add_paragraph(line)
    buf = io.BytesIO(); d.save(buf)
    return buf.getvalue()


def token():
    from sqlalchemy import create_engine, text
    with create_engine(ENV["DATABASE_URL"]).connect() as c:
        row = c.execute(text("select id from users where email = :e"), {"e": DEMO_EMAIL}).first()
    if not row:
        sys.exit(f"{DEMO_EMAIL} not found. Create it in the app first.")
    return jwt.encode({"sub": str(row[0]), "exp": int(time.time()) + 3600}, ENV["SECRET_KEY"], algorithm="HS256")


def strings(obj, prefix=""):
    """All leaf string values of profile_data with their paths (derived numbers are skipped)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from strings(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from strings(v, f"{prefix}[{i}]")
    elif isinstance(obj, str) and obj.strip():
        yield prefix, obj


def main():
    print("== Task 2: CV Agent ==")
    try:
        requests.get(f"{API}/health", timeout=5)
    except requests.RequestException:
        sys.exit("Backend is not running on 127.0.0.1:8000. Start it and run again.")
    h = {"Authorization": f"Bearer {token()}"}

    print("\n-- 1. Read a CV for review (/documents/parse, DOCX, nothing saved)")
    t0 = time.time()
    r = requests.post(f"{API}/documents/parse", headers=h, timeout=180,
                      files={"file": ("Jordan_Avery_CV.docx", docx_bytes(),
                                      "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
    print(f"  HTTP {r.status_code} in {time.time() - t0:.1f}s")
    if r.status_code != 200:
        print(r.text[:400]); return finish()
    body = r.json()
    p = body["profile_data"]
    check("AI extraction used (not the fallback)", body.get("extraction_method") == "llm", body.get("extraction_method"))
    rows = list(strings({k: v for k, v in p.items()}))
    print(f"\n  {'value':60} in CV?")
    found = 0
    for path, value in rows:
        ok = in_cv(value) or (path.endswith("description") and sum(w in norm(CV_TEXT) for w in map(norm, value.split())) >= 0.7 * max(1, len(value.split())))
        found += ok
        print(f"  {(path + ': ' + value)[:60]:60} {'yes' if ok else 'NO'}")
    check("every extracted value is in the CV", found == len(rows), f"{found}/{len(rows)}")
    if body.get("dropped"):
        print(f"  grounding check removed {len(body['dropped'])} AI value(s): {body['dropped'][:5]}")
    check("years of experience = 7 (from the CV)", p.get("professional", {}).get("experience_years") == 7,
          p.get("professional", {}).get("experience_years"))
    check("2 jobs and 1 degree found", len(p.get("experience", [])) == 2 and len(p.get("education", [])) == 1,
          f"{len(p.get('experience', []))} jobs, {len(p.get('education', []))} degrees")
    skills = [s for v in (p.get("skills") or {}).values() for s in v]
    check("each skill listed once", len(skills) == len({s.lower() for s in skills}), ", ".join(skills))

    print("\n-- 2. Upload to the profile (/documents/upload): facts must wait for confirmation")
    t0 = time.time()
    r = requests.post(f"{API}/documents/upload", headers=h, timeout=180,
                      files={"file": ("Jordan_Avery_CV.txt", CV_TEXT.encode(), "text/plain")})
    print(f"  HTTP {r.status_code} in {time.time() - t0:.1f}s")
    up = r.json() if r.ok else {}
    check("upload saved new facts as 'needs review' (already-confirmed identical values stay confirmed)", r.ok and up.get("needs_review", 0) > 0,
          f"{up.get('needs_review')} need review, conflicts: {up.get('conflicts')}")
    ids = [f["id"] for f in up.get("facts", [])]
    c = requests.post(f"{API}/profiles/me/facts/confirm", headers=h, json={"fact_ids": ids, "action": "confirm"}, timeout=30)
    prof = requests.get(f"{API}/profiles/me", headers=h, timeout=30).json()
    verified = [f for f in prof.get("facts", []) if f.get("verified")]
    check("confirm marks them verified", c.ok and len(verified) >= len(ids), f"{len(verified)} verified facts")

    print("\n-- 3. Tailor Resume with the real model")
    cv = {"title": "Senior Data Engineer", "summary": p.get("professional", {}).get("summary", ""),
          "experience": [{"role": e.get("title", ""), "company": e.get("company", ""), "period": f"{e.get('start_date', '')} - {e.get('end_date', '')}",
                          "bullets": [b.strip() for b in e.get("description", "").split("|") if b.strip()]} for e in p.get("experience", [])],
          "skills": skills, "education": [], "certifications": p.get("certifications", [])}
    t0 = time.time()
    r = requests.post(f"{API}/resumes/tailor", headers=h, timeout=180, json={
        "target_role": "Analytics Engineer", "cv": cv,
        "job_description": "Analytics Engineer: build dbt models and Airflow pipelines on Snowflake; Python and SQL required."})
    check("Tailor Resume answered", r.status_code == 200, f"HTTP {r.status_code} in {time.time() - t0:.1f}s")

    snap = requests.get(f"{API}/agent-runs/snapshot?range=1h", headers=h, timeout=10).json()
    print("\n-- Dashboard (latest CV agent runs)")
    for run in [x for x in snap["runs"] if x["agent"] == "cv"][:3]:
        tools = ", ".join(f"{t['name']} {t['status']} {t.get('duration_ms', '-')}ms" for t in run["tool_calls"])
        print(f"  {run['task']} | {run['status']} | {tools}")
    finish()


def finish():
    print(f"\nRESULT: {sum(results)}/{len(results)} checks passed")


if __name__ == "__main__":
    main()

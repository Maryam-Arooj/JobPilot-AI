"""One-click "Apply with AI": CV -> live jobs -> best match -> recruiter email -> research + email + CV -> your approval.
Runs in the background; each agent records its own live run on the Agent Transparency dashboard.
The Gmail draft is NEVER created here: the last step waits for the user's approval."""
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

STEPS = [
    ("cv", "CV Agent: read your CV"),
    ("job", "Job Agent: find live jobs for your CV"),
    ("email", "Email Agent: find real recruiter emails"),
    ("job", "Job Agent: pick the best match"),
    ("email", "Email Agent: research company, write email, attach CV"),
    ("you", "You: review and approve the Gmail draft"),
]
_P: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()


def start(user_id: int, location: Optional[str], mode: str, require_email: bool, max_jobs: int) -> str:
    pid = uuid.uuid4().hex[:12]
    with _LOCK:
        _P[pid] = {"user_id": user_id, "status": "running", "started": time.time(), "error": None,
                   "application_id": None, "job": None, "recipient": "", "message": "",
                   "steps": [{"agent": a, "name": n, "status": "pending", "detail": ""} for a, n in STEPS]}
    threading.Thread(target=_run, args=(pid, user_id, location, mode, require_email, max_jobs), daemon=True).start()
    return pid


def get(pid: str, user_id: int) -> Optional[Dict[str, Any]]:
    p = _P.get(pid)
    if not p or p["user_id"] != user_id:
        return None
    return {k: v for k, v in p.items() if k != "user_id"} | {"elapsed": round(time.time() - p["started"])}


def _step(p: Dict[str, Any], i: int, status: str, detail: str = "") -> None:
    with _LOCK:
        p["steps"][i]["status"] = status
        if detail:
            p["steps"][i]["detail"] = detail


def _run(pid: str, user_id: int, location: Optional[str], mode: str, require_email: bool, max_jobs: int) -> None:
    from ..api.applications import ApplicationCreate, create_application
    from ..api.jobs import FromCvRequest, jobs_from_cv, _profile_dict
    from ..db.database import SessionLocal
    from ..models.career_profile import CareerProfile
    from ..services import recipients
    from ..services.job_matching import candidate_skills, candidate_title
    p = _P[pid]
    db = SessionLocal()
    i = 0
    try:
        # 1. CV
        _step(p, 0, "running")
        profile = _profile_dict(db.query(CareerProfile).filter(CareerProfile.user_id == user_id).first())
        title, skills = candidate_title(profile), candidate_skills(profile)
        if not (title or skills):
            raise RuntimeError("No CV found. Upload your CV on the Confirm page first.")
        _step(p, 0, "done", f"{title or 'Your role'} · {len(skills)} skills")

        # 2. jobs
        i = 1; _step(p, 1, "running")
        res = jobs_from_cv(FromCvRequest(location=location, mode=mode), user_id=user_id, db=db)
        ranked: List[Dict[str, Any]] = res.get("results") or []
        if not ranked:
            raise RuntimeError(f"No live jobs found for {res.get('query')} ({res.get('searched')}). Try another location.")
        _step(p, 1, "done", f"{len(ranked)} jobs for \"{res.get('query')}\" ({res.get('searched')})")

        # 3. recipient emails for the best matches (grouped by company, 3 at a time)
        i = 2; _step(p, 2, "running")
        top = [r for r in ranked if r.get("match_score") is not None][:max_jobs] or ranked[:max_jobs]
        task_id = uuid.uuid4().hex[:12]
        recipients._TASKS[task_id] = {"user_id": user_id, "status": "running", "total": 0, "done": 0, "found": {},
                                      "started": time.time(), "error": None}
        recipients._run_batch(task_id, user_id, [r["id"] for r in top])
        found = recipients._TASKS[task_id]["found"]
        with_email = [r for r in top if found.get(r["id"])]
        _step(p, 2, "done", f"{len(with_email)} of {len(top)} top jobs have a real recruiter email")

        # 4. pick
        i = 3; _step(p, 3, "running")
        best = with_email[0] if with_email else None
        if not best:
            if require_email:
                raise RuntimeError(f"None of the top {len(top)} jobs publish a recruiter email. Try Pakistan or another "
                                   "location, or switch off 'only jobs with a recruiter email'.")
            best = top[0]
        recipient = (found.get(best["id"]) or [""])[0]
        with _LOCK:
            p["job"] = {"id": best["id"], "title": best["title"], "company": best["company"],
                        "location": best.get("location"), "match_score": best.get("match_score")}
            p["recipient"] = recipient
        score = f"{best['match_score']}% match" if best.get("match_score") is not None else "match not scored"
        _step(p, 3, "done", f"{best['title']} at {best['company']} ({score})")

        # 5. application: research + email + CV
        i = 4; _step(p, 4, "running")
        app = create_application(ApplicationCreate(job_id=best["id"]), user_id=user_id, db=db)
        research = ((app.get("company") or {}).get("research") or {}).get("status")
        cv = (app.get("cv_attachment") or {}).get("label") or "no CV found"
        with _LOCK:
            p["application_id"] = app["id"]
        _step(p, 4, "done", f"Email written · company research: {research} · attachment: {cv}")

        # 6. waits for the user
        _step(p, 5, "waiting", f"Open the application and approve the draft to {recipient or 'the recruiter'}")
        with _LOCK:
            p["status"] = "ready"
            p["message"] = "Ready. Nothing was sent: review the email and approve the Gmail draft."
    except HTTPException as e:
        _step(p, i, "failed", str(e.detail))
        with _LOCK:
            p["status"], p["error"] = "failed", str(e.detail)
    except Exception as e:
        _step(p, i, "failed", str(e)[:300])
        with _LOCK:
            p["status"], p["error"] = "failed", str(e)[:300]
    finally:
        db.close()

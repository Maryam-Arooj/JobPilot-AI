"""Background AI refinement of a CV after the instant quick read.

/documents/parse and /documents/upload return the quick literal result in seconds and start this
job; the frontend polls GET /documents/refine/{job_id}. Jobs live in memory (single backend process)
and expire after an hour. Every job is a tracked run on the live dashboard.
"""
import threading
import time
import uuid
from typing import Any, Dict, Optional

from ..ai_agents.profile_agent import ProfileAgent
from ..db.database import SessionLocal
from .agent_runs import track_run

_JOBS: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()
TTL_SECONDS = 3600


def _cleanup() -> None:
    cutoff = time.time() - TTL_SECONDS
    for k in [k for k, v in _JOBS.items() if v["created"] < cutoff]:
        _JOBS.pop(k, None)


def _run(job_id: str, user_id: int, text: str, filename: str, save_source: Optional[str]) -> None:
    job = _JOBS[job_id]
    try:
        with track_run(user_id, "cv", f"AI refinement: {filename}", input_summary={"filename": filename, "text_chars": len(text)}) as run:
            run.step("AI extraction and grounding check", 1, 2 if save_source else 1)
            result = ProfileAgent().extract_from_text(text)
            if save_source and result.get("extraction_method") == "llm":
                run.step("Update saved profile (facts need your review)", 2, 2)
                from .profile_ingest import save_extraction
                db = SessionLocal()
                try:
                    saved = save_extraction(db, user_id, result, source=save_source)
                    db.commit()
                    result = {**result, "facts": saved["facts"], "needs_review": saved["needs_review"], "conflicts": saved["conflicts"]}
                finally:
                    db.close()
            run.set_output({"extraction_method": result.get("extraction_method"), "facts": len(result.get("facts", [])),
                            "dropped_values": len(result.get("dropped", []))})
        with _LOCK:
            job.update(status="done" if result.get("extraction_method") == "llm" else "failed",
                       result=result, finished=time.time(),
                       error=None if result.get("extraction_method") == "llm" else (result.get("message") or "AI refinement unavailable"))
    except Exception as e:  # never leave a job hanging
        with _LOCK:
            job.update(status="failed", error=str(e)[:300], finished=time.time())


def start(user_id: int, text: str, filename: str, save_source: Optional[str] = None) -> str:
    job_id = uuid.uuid4().hex
    with _LOCK:
        _cleanup()
        _JOBS[job_id] = {"user_id": user_id, "status": "running", "created": time.time(), "result": None, "error": None}
    threading.Thread(target=_run, args=(job_id, user_id, text, filename, save_source), daemon=True).start()
    return job_id


def get(job_id: str, user_id: int) -> Optional[Dict[str, Any]]:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job or job["user_id"] != user_id:
            return None
        return dict(job)

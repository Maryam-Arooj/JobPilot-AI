"""Live agent dashboard API. Contract: frontend/src/features/agent-transparency/types.ts"""
from datetime import timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..models.agent_runs import AgentRun
from ..services.agent_runs import AGENTS, STALE_AFTER_SECONDS, iso, utcnow
from ..services.auth_middleware import get_current_user_id

router = APIRouter(prefix="/agent-runs", tags=["agent-runs"])

RANGES = {"1h": timedelta(hours=1), "24h": timedelta(hours=24), "7d": timedelta(days=7)}
RUN_LIMIT = 100
TIMELINE_LIMIT = 200
TIMELINE_TYPES = {"started", "finished", "failed", "tool_failed", "warning"}


def _aware(dt):
    from datetime import timezone
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _expire_stale_runs(db: Session, user_id: int) -> None:
    """Runs still 'running' after 10 minutes never reported completion (e.g. server restart)."""
    cutoff = utcnow() - timedelta(seconds=STALE_AFTER_SECONDS)
    stale = (db.query(AgentRun)
             .filter(AgentRun.user_id == user_id, AgentRun.status == "running")
             .all())
    changed = False
    for run in stale:
        if _aware(run.started_at) < cutoff:
            run.status = "failed"
            run.finished_at = utcnow()
            run.error = "Timed out: no completion was recorded within 10 minutes (the server may have restarted)."
            run.current_step = None
            run.logs = list(run.logs or []) + [{"at": iso(utcnow()), "level": "error", "message": run.error}]
            run.events = list(run.events or []) + [{"at": iso(utcnow()), "type": "failed",
                                                    "detail": f"{run.task} timed out", "status": "failed"}]
            changed = True
    if changed:
        db.commit()


def serialize_run(run: AgentRun) -> Dict[str, Any]:
    output = run.output_summary
    if run.error:
        output = dict(output or {})
        output.setdefault("error", run.error)
    return {
        "id": run.id,
        "agent": run.agent,
        "task": run.task,
        "status": run.status,
        "started_at": iso(run.started_at),
        "finished_at": iso(run.finished_at),
        "correlation_id": run.correlation_id or run.id,
        "retry_count": run.retry_count or 0,
        "current_step": run.current_step if run.status == "running" else None,
        "input": run.input_summary or {},
        "output": output,
        "error": run.error,
        "tool_calls": list(run.tool_calls or []),
        "logs": list(run.logs or []),
        "events": list(run.events or []),
    }


def _agent_status(agent: str, runs_in_range: List[AgentRun], latest: Optional[AgentRun]) -> Dict[str, Any]:
    mine = [r for r in runs_in_range if r.agent == agent]
    running = next((r for r in mine if r.status == "running"), None)
    last_activity = None
    if latest is not None:
        last_activity = iso(latest.finished_at or latest.started_at)
        for e in reversed(latest.events or []):
            last_activity = e.get("at") or last_activity
            break
    if running is not None:
        return {"agent": agent, "state": "running", "current_task": running.task,
                "started_at": iso(running.started_at), "last_activity_at": last_activity}
    if mine and mine[0].status == "failed":
        return {"agent": agent, "state": "error", "current_task": mine[0].task,
                "started_at": iso(mine[0].started_at), "last_activity_at": last_activity}
    return {"agent": agent, "state": "idle",
            "current_task": (mine[0].task if mine else "No runs in this period"),
            "started_at": None, "last_activity_at": last_activity}


def _timeline(runs: List[AgentRun]) -> List[Dict[str, Any]]:
    items = []
    for run in runs:
        for i, ev in enumerate(run.events or []):
            if ev.get("type") not in TIMELINE_TYPES:
                continue
            status = ev.get("status") or run.status
            items.append({
                "id": f"{run.id}:{i}",
                "at": ev.get("at") or iso(run.started_at),
                "agent": run.agent,
                "title": {"started": "Started", "finished": "Completed", "failed": "Failed",
                          "tool_failed": "API call failed", "warning": "Warning"}.get(ev.get("type"), ev.get("type")),
                "detail": ev.get("detail", ""),
                "status": status,
                "run_id": run.id,
            })
    items.sort(key=lambda x: x["at"] or "", reverse=True)
    return items[:TIMELINE_LIMIT]


@router.get("/snapshot")
def get_snapshot(range: str = Query("24h"), user_id: int = Depends(get_current_user_id),
                 db: Session = Depends(get_db)):
    window = RANGES.get(range)
    if window is None:
        raise HTTPException(status_code=400, detail="range must be one of 1h, 24h, 7d")
    _expire_stale_runs(db, user_id)
    since = utcnow() - window
    runs = (db.query(AgentRun)
            .filter(AgentRun.user_id == user_id)
            .filter((AgentRun.started_at >= since) | (AgentRun.status == "running"))
            .order_by(AgentRun.started_at.desc())
            .limit(RUN_LIMIT)
            .all())
    agents = []
    for agent in AGENTS:
        latest = (db.query(AgentRun)
                  .filter(AgentRun.user_id == user_id, AgentRun.agent == agent)
                  .order_by(AgentRun.started_at.desc())
                  .first())
        agents.append(_agent_status(agent, runs, latest))
    return {
        "generated_at": iso(utcnow()),
        "range": range,
        "agents": agents,
        "runs": [serialize_run(r) for r in runs],
        "timeline": _timeline(runs),
    }


@router.get("/{run_id}")
def get_run(run_id: str, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    run = db.query(AgentRun).filter(AgentRun.id == run_id, AgentRun.user_id == user_id).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return serialize_run(run)

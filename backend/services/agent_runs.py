"""Agent run tracking for the live dashboard (/agent-runs/snapshot).

Usage in an endpoint:

    with track_run(user_id, "job", f"Search jobs: {query}", input_summary={"query": query}) as run:
        run.step("Search providers", 1, 3)
        with tool_call("serpapi.google_jobs", f"query={query}") as t:
            results = provider.search(...)
            t["summary"] = f"{len(results)} results"
        ...
        run.set_output({"saved_jobs": n})

Code deeper in the call stack (agents, providers, the NVIDIA client) uses the module helpers
tool_call() / run_log() / run_step(), which do nothing when no run is active.

Guarantees:
- Every write goes through its own short-lived DB session and is committed immediately, so the
  dashboard sees "running" runs and step changes while the request is still in progress.
- Tracking never breaks the request: DB errors while tracking are logged and swallowed.
- Everything stored is sanitised: secrets are redacted, strings truncated, documents never stored.
"""
from __future__ import annotations

import contextvars
import logging
import re
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

from ..db.database import SessionLocal
from ..models.agent_runs import AgentRun

logger = logging.getLogger(__name__)

AGENTS = ("cv", "job", "email")
MAX_STR = 300
MAX_LIST = 20
MAX_DEPTH = 4
MAX_ENTRIES = 200  # per run, for tool_calls / logs / events
STALE_AFTER_SECONDS = 10 * 60

_current_run: contextvars.ContextVar[Optional["RunHandle"]] = contextvars.ContextVar("agent_run", default=None)

_SECRET_PATTERNS = [
    re.compile(r"nvapi-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"apify_api_[A-Za-z0-9]{8,}"),
    re.compile(r"\bfc-[A-Za-z0-9]{16,}"),
    re.compile(r"GOCSPX-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\bya29\.[A-Za-z0-9._\-]{10,}"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password|client[_-]?secret)\s*[=:]\s*[^\s&,;\"']+"),
    re.compile(r"\b[a-f0-9]{40,}\b"),  # long hex keys (e.g. SerpAPI)
    re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}"),  # JWTs
]
_SECRET_KEY_NAMES = re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization|credential|cookie)")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:  # SQLite returns naive datetimes; we always store UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def redact(text: str) -> str:
    for pat in _SECRET_PATTERNS:
        text = pat.sub("[redacted]", text)
    return text


def sanitize(value: Any, depth: int = 0) -> Any:
    """Make a value safe and small enough to store and show on the dashboard."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        text = redact(value)
        return text if len(text) <= MAX_STR else text[:MAX_STR] + f"… ({len(value)} chars)"
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    if depth >= MAX_DEPTH:
        return "…"
    if isinstance(value, dict):
        out = {}
        for i, (k, v) in enumerate(value.items()):
            if i >= MAX_LIST:
                out["…"] = f"{len(value) - MAX_LIST} more keys"
                break
            key = str(k)
            out[key] = "[redacted]" if _SECRET_KEY_NAMES.search(key) else sanitize(v, depth + 1)
        return out
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        out = [sanitize(v, depth + 1) for v in items[:MAX_LIST]]
        if len(items) > MAX_LIST:
            out.append(f"… {len(items) - MAX_LIST} more")
        return out
    return sanitize(str(value), depth)


class RunHandle:
    """A live agent run. All mutators persist immediately (best effort)."""

    def __init__(self, run_id: str, user_id: int, agent: str, task: str):
        self.id = run_id
        self.user_id = user_id
        self.agent = agent
        self.task = task
        self.status = "running"
        self.error: Optional[str] = None
        self.tool_calls: List[Dict[str, Any]] = []
        self.logs: List[Dict[str, Any]] = []
        self.events: List[Dict[str, Any]] = []
        self.current_step: Optional[Dict[str, Any]] = None
        self.output: Optional[Dict[str, Any]] = None
        self._lock = threading.Lock()
        self._failed_explicitly = False

    # -- persistence -------------------------------------------------------
    def _save(self, **fields: Any) -> None:
        db = SessionLocal()
        try:
            row = db.get(AgentRun, self.id)
            if row is None:
                return
            for k, v in fields.items():
                setattr(row, k, v)
            db.commit()
        except Exception:  # tracking must never break the real request
            db.rollback()
            logger.warning("agent run tracking write failed for run %s", self.id, exc_info=True)
        finally:
            db.close()

    def _append(self, kind: str, entry: Dict[str, Any]) -> None:
        with self._lock:
            target: List[Dict[str, Any]] = getattr(self, kind)
            if len(target) >= MAX_ENTRIES:
                return
            target.append(entry)
            snapshot = [dict(e) for e in target]
        self._save(**{kind: snapshot})

    # -- public API --------------------------------------------------------
    def log(self, level: str, message: str) -> None:
        level = level if level in ("info", "warn", "error") else "info"
        self._append("logs", {"at": iso(utcnow()), "level": level, "message": sanitize(message)})

    def event(self, type_: str, detail: str, status: Optional[str] = None) -> None:
        entry = {"at": iso(utcnow()), "type": type_, "detail": sanitize(detail)}
        if status:
            entry["status"] = status
        self._append("events", entry)

    def step(self, label: str, index: int, total: int) -> None:
        total = max(1, int(total))
        index = max(1, min(int(index), total))
        self.current_step = {"label": sanitize(label), "index": index, "total": total,
                             "pct": int(round((index - 1) / total * 100))}
        self._save(current_step=dict(self.current_step))
        self.event("step", f"Step {index}/{total}: {label}", status="running")

    def warn(self, message: str) -> None:
        self.log("warn", message)
        self.event("warning", message, status="pending")

    def set_output(self, output: Dict[str, Any]) -> None:
        self.output = sanitize(output)
        self._save(output_summary=self.output)

    def fail(self, message: str) -> None:
        """Mark the run failed without raising (e.g. the endpoint returns an honest error body)."""
        self._failed_explicitly = True
        self.error = sanitize(message)

    @contextmanager
    def tool(self, name: str, summary: str = "") -> Iterator[Dict[str, Any]]:
        """Time an external call (API, model, parser). Set info["summary"] to record the result."""
        info: Dict[str, Any] = {"summary": summary}
        call = {"id": uuid.uuid4().hex[:12], "name": sanitize(name), "at": iso(utcnow()),
                "summary": sanitize(summary), "status": "running"}
        with self._lock:
            index = len(self.tool_calls)
            if index < MAX_ENTRIES:
                self.tool_calls.append(call)
            snapshot = [dict(e) for e in self.tool_calls]
        self._save(tool_calls=snapshot)
        started = time.perf_counter()
        try:
            yield info
        except BaseException as exc:
            self._finish_tool(index, "failed", started,
                              f"{info.get('summary') or summary} — failed: {_error_text(exc)}".strip(" —"))
            self.event("tool_failed", f"{name} failed: {_error_text(exc)}", status="failed")
            raise
        else:
            self._finish_tool(index, info.get("status", "success"), started, info.get("summary", summary))

    def _finish_tool(self, index: int, status: str, started: float, summary: str) -> None:
        with self._lock:
            if index >= len(self.tool_calls):
                return
            self.tool_calls[index].update({
                "status": status if status in ("success", "failed") else "success",
                "duration_ms": int((time.perf_counter() - started) * 1000),
                "summary": sanitize(summary or ""),
            })
            snapshot = [dict(e) for e in self.tool_calls]
        self._save(tool_calls=snapshot)


def _error_text(exc: BaseException) -> str:
    detail = getattr(exc, "detail", None)  # FastAPI HTTPException
    if detail:
        return redact(str(detail))[:MAX_STR]
    text = str(exc) or type(exc).__name__
    return redact(text)[:MAX_STR]


@contextmanager
def track_run(user_id: int, agent: str, task: str, input_summary: Optional[Dict[str, Any]] = None,
              correlation_id: Optional[str] = None) -> Iterator[RunHandle]:
    """Record one agent run. Exceptions (incl. HTTPException) mark it failed and are re-raised."""
    if agent not in AGENTS:
        raise ValueError(f"unknown agent {agent!r}")
    run_id = str(uuid.uuid4())
    handle = RunHandle(run_id, user_id, agent, task)
    started_at = utcnow()
    db = SessionLocal()
    try:
        db.add(AgentRun(
            id=run_id, user_id=user_id, agent=agent, task=sanitize(task)[:300], status="running",
            started_at=started_at, correlation_id=correlation_id or uuid.uuid4().hex[:16], retry_count=0,
            input_summary=sanitize(input_summary or {}), tool_calls=[], logs=[], events=[],
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("could not create agent run record", exc_info=True)
    finally:
        db.close()
    handle.event("started", f"{task} started", status="running")

    token = _current_run.set(handle)
    try:
        yield handle
    except BaseException as exc:
        message = _error_text(exc)
        handle.log("error", message)
        handle.event("failed", f"{task} failed: {message}", status="failed")
        handle._save(status="failed", error=sanitize(message), finished_at=utcnow(), current_step=None)
        raise
    else:
        if handle._failed_explicitly:
            handle.log("error", handle.error or "failed")
            handle.event("failed", f"{task} failed: {handle.error}", status="failed")
            handle._save(status="failed", error=handle.error, finished_at=utcnow(), current_step=None)
        else:
            handle.event("finished", f"{task} completed", status="success")
            handle._save(status="success", finished_at=utcnow(), current_step=None)
    finally:
        _current_run.reset(token)


# -- helpers usable anywhere in the call stack (no-ops without an active run) --------------

def current_run() -> Optional[RunHandle]:
    return _current_run.get()


@contextmanager
def tool_call(name: str, summary: str = "") -> Iterator[Dict[str, Any]]:
    run = _current_run.get()
    if run is None:
        yield {"summary": summary}
        return
    with run.tool(name, summary) as info:
        yield info


def run_log(level: str, message: str) -> None:
    run = _current_run.get()
    if run is not None:
        run.log(level, message)


def run_warn(message: str) -> None:
    run = _current_run.get()
    if run is not None:
        run.warn(message)


def run_step(label: str, index: int, total: int) -> None:
    run = _current_run.get()
    if run is not None:
        run.step(label, index, total)

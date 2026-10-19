"""Print the latest agent runs (steps, tool calls, logs, output) from the database. Never prints keys.

Usage (repo root):
    backend\\.venv\\Scripts\\python.exe backend\\scripts\\show_last_runs.py                # last 3 CV runs, all users
    backend\\.venv\\Scripts\\python.exe backend\\scripts\\show_last_runs.py job 5          # last 5 Job agent runs
"""
import json
import sys
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text

ENV = {k: (v or "").strip() for k, v in dotenv_values(Path(__file__).resolve().parent.parent / ".env").items()}
agent = sys.argv[1] if len(sys.argv) > 1 else "cv"
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 3

with create_engine(ENV["DATABASE_URL"]).connect() as c:
    rows = c.execute(text(
        "select r.task, r.status, r.started_at, r.finished_at, r.error, r.tool_calls, r.logs, r.events, "
        "r.output_summary, u.email from agent_runs r join users u on u.id = r.user_id "
        "where r.agent = :a order by r.started_at desc limit :n"), {"a": agent, "n": limit}).fetchall()

def js(v):
    return v if isinstance(v, (list, dict)) else json.loads(v or "null")

for task, status, started, finished, error, tools, logs, events, output, email in rows:
    print("=" * 100)
    print(f"{task}  [{status}]  user={email}  {started} -> {finished}")
    if error:
        print(f"  ERROR: {error}")
    for t in js(tools) or []:
        print(f"  tool  {t.get('name', ''):45} {t.get('status', ''):8} {t.get('duration_ms', '-')} ms  {t.get('summary', '')}")
    for l in js(logs) or []:
        print(f"  log   {l.get('level', ''):5} {l.get('message', '')}")
    print(f"  output {json.dumps(js(output))[:600]}")
if not rows:
    print(f"No {agent} runs found.")

"""Benchmark NVIDIA NIM models/settings on a realistic CV-extraction task.

Usage (from the repo root):
    backend\\.venv\\Scripts\\python.exe backend\\scripts\\bench_nvidia_extraction.py [--runs 2] [--out results.json]

Every config gets the same fictional CV and the same prompt. For each run we record time,
completion tokens, finish_reason, whether the content parsed as JSON, and a grounding check:
every leaf value must appear in the CV verbatim, or (for longer text) be built from the CV's
own words; any number not in the CV counts as invented. Keys are never printed.
"""
import argparse
import json
import re
import sys
import threading
import time
from pathlib import Path

import requests
from dotenv import dotenv_values

ENV = {k: (v or "").strip() for k, v in dotenv_values(Path(__file__).resolve().parent.parent / ".env").items()}
KEY = ENV.get("OPENAI_API_KEY", "")
BASE = (ENV.get("OPENAI_BASE_URL") or "https://integrate.api.nvidia.com/v1").rstrip("/")

# Fictional person and companies, written for this benchmark.
CV_TEXT = """\
Priya Ramanathan
Senior Backend Engineer
Pune, India | priya.ramanathan.dev@example.com | +91 98220 41735
linkedin.com/in/priya-ramanathan-dev | github.com/priyar-dev

SUMMARY
Backend engineer with 7 years of experience designing payment and logistics platforms in Python and Go.
Focused on reliable distributed systems, clean APIs and mentoring junior developers.

EXPERIENCE
Senior Backend Engineer — Kestrel Payments, Pune (March 2021 – Present)
- Led the redesign of the settlement service in Go, reducing reconciliation errors by 35%.
- Built an event-driven ledger on Kafka and PostgreSQL processing 2 million transactions per day.
- Mentored a team of 4 junior engineers and introduced weekly design reviews.

Software Engineer — Bluefin Logistics, Bengaluru (July 2017 – February 2021)
- Developed route-planning APIs in Python (FastAPI) used by 120 warehouse partners.
- Migrated batch jobs from cron to Airflow, cutting nightly runtime from 6 hours to 90 minutes.

EDUCATION
B.Tech in Computer Engineering — College of Engineering Pune, 2017

SKILLS
Python, Go, FastAPI, PostgreSQL, Kafka, Redis, Docker, Kubernetes, Airflow, AWS

PROJECTS
OpenLedger Lite — open-source double-entry bookkeeping library in Go (github.com/priyar-dev/openledger-lite).
ShipTrack — personal dashboard for tracking parcel deliveries, built with FastAPI and React.

CERTIFICATIONS
AWS Certified Developer – Associate (2022)
Certified Kubernetes Application Developer (CKAD), 2023
"""

SCHEMA_PROMPT = """Extract the career profile from the CV below into this JSON shape. Copy values exactly as written
in the CV. Use "" or [] when something is not in the CV. Never add anything that is not in the CV.

{
  "personal": {"name": "", "email": "", "phone": "", "location": "", "linkedin": "", "github": ""},
  "professional": {"headline": "", "summary": "", "years_of_experience": ""},
  "skills": [""],
  "experience": [{"title": "", "company": "", "location": "", "start_date": "", "end_date": "", "highlights": [""]}],
  "education": [{"degree": "", "institution": "", "year": ""}],
  "projects": [{"name": "", "description": ""}],
  "certifications": [{"name": "", "year": ""}]
}

CV:
---
""" + CV_TEXT + "---"

SYSTEM = "You extract structured data from CVs. Output one JSON object only: no prose, no markdown, no code fences."
JSON_FORMAT = {"response_format": {"type": "json_object"}}

LIGHTNING = "nvidia/nemotron-3.5-lightning-30b-a3b"
SUPER = "nvidia/nemotron-3-super-120b-a12b"
GPTOSS = "openai/gpt-oss-20b"
LLAMA = "meta/llama-3.2-11b-vision-instruct"
THINK_OFF = {"chat_template_kwargs": {"enable_thinking": False}}

# (label, model, system prefix, extra request body, max_tokens)
CONFIGS = [
    ("llama baseline", LLAMA, "", {}, 3000),
    ("lightning /no_think", LIGHTNING, "/no_think\n", {}, 3000),
    ("lightning enable_thinking=false", LIGHTNING, "", THINK_OFF, 3000),
    ("lightning thinking off + json_object", LIGHTNING, "", {**THINK_OFF, **JSON_FORMAT}, 3000),
    ("super /no_think", SUPER, "/no_think\n", {}, 3000),
    ("super enable_thinking=false", SUPER, "", THINK_OFF, 3000),
    ("super thinking off + json_object", SUPER, "", {**THINK_OFF, **JSON_FORMAT}, 3000),
    ("super low_effort thinking", SUPER, "", {"chat_template_kwargs": {"enable_thinking": True, "low_effort": True}}, 6000),
    ("gpt-oss reasoning_effort=low", GPTOSS, "", {"reasoning_effort": "low"}, 6000),
    ("gpt-oss system 'Reasoning: low'", GPTOSS, "Reasoning: low\n", {}, 6000),
    ("gpt-oss low + json_object", GPTOSS, "", {"reasoning_effort": "low", **JSON_FORMAT}, 6000),
]

NORM = lambda s: re.sub(r"\s+", " ", str(s)).strip().lower()
CV_NORM = NORM(CV_TEXT.replace("–", "-").replace("—", "-"))
CV_WORDS = set(re.findall(r"[a-z0-9+#.]+", CV_NORM))
CV_NUMBERS = set(re.findall(r"\d+", CV_TEXT))


def leaves(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from leaves(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from leaves(v, f"{path}[{i}]")
    elif obj not in (None, "", True, False):
        yield path, obj


def grounding(data):
    verbatim, paraphrase, ungrounded, invented_numbers = 0, 0, [], set()
    for path, value in leaves(data):
        v = NORM(str(value).replace("–", "-").replace("—", "-"))
        invented_numbers |= set(re.findall(r"\d+", str(value))) - CV_NUMBERS
        if v in CV_NORM:
            verbatim += 1
            continue
        words = [w for w in re.findall(r"[a-z0-9+#.]+", v) if len(w) > 3]
        if words and sum(w in CV_WORDS for w in words) / len(words) >= 0.9:
            paraphrase += 1
        else:
            ungrounded.append(f"{path}={str(value)[:50]!r}")
    return verbatim, paraphrase, ungrounded, sorted(invented_numbers)


def parse(text):
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip(), flags=re.I)
    try:
        return json.loads(t)
    except ValueError:
        s, e = t.find("{"), t.rfind("}")
        if s != -1 and e > s:
            try:
                return json.loads(t[s:e + 1])
            except ValueError:
                return None
    return None


def run_one(label, model, prefix, extra, max_tokens):
    body = {"model": model, "temperature": 0.2, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": prefix + SYSTEM}, {"role": "user", "content": SCHEMA_PROMPT}],
            **extra}
    t0 = time.perf_counter()
    try:
        r = requests.post(f"{BASE}/chat/completions", json=body, timeout=240,
                          headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
        secs = time.perf_counter() - t0
    except requests.RequestException as e:
        return {"label": label, "secs": round(time.perf_counter() - t0, 1), "http": None, "error": type(e).__name__}
    out = {"label": label, "secs": round(secs, 1), "http": r.status_code}
    if r.status_code != 200:
        try:
            err = r.json()
            e = err.get("error")
            msg = err.get("detail") or err.get("title") or (e.get("message") if isinstance(e, dict) else e)
        except (ValueError, AttributeError):
            msg = r.text[:120]
        out["error"] = re.sub(r"\s*for account '[^']*'|Function '[^']*':?\s*", "", str(msg))[:140]
        return out
    j = r.json()
    choice = (j.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    content = msg.get("content") or ""
    out.update(finish=choice.get("finish_reason"), tokens=(j.get("usage") or {}).get("completion_tokens"),
               reasoning_chars=len(msg.get("reasoning_content") or msg.get("reasoning") or ""))
    data = parse(content)
    out["json"] = isinstance(data, dict)
    if out["json"]:
        v, p, u, nums = grounding(data)
        out.update(values=v + p + len(u), verbatim=v, paraphrase=p, ungrounded=u, invented_numbers=nums,
                   experience=len(data.get("experience") or []), skills=len(data.get("skills") or []))
    else:
        out["content_head"] = content[:80]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--out", default="")
    ap.add_argument("--only", default="", help="substring filter on config labels")
    args = ap.parse_args()
    if not KEY:
        sys.exit("OPENAI_API_KEY not set in backend/.env")
    configs = [c for c in CONFIGS if args.only.lower() in c[0].lower()]
    results, lock = [], threading.Lock()

    def worker(model):  # one thread per model: runs on the same model never overlap
        for cfg in [c for c in configs if c[1] == model]:
            for n in range(1, args.runs + 1):
                res = run_one(*cfg)
                res["run"] = n
                with lock:
                    results.append(res)
                    print(f"done: {res['label']} run {n}: {res.get('secs')}s http={res.get('http')} json={res.get('json')}", flush=True)

    threads = [threading.Thread(target=worker, args=(m,)) for m in dict.fromkeys(c[1] for c in configs)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    order = {c[0]: i for i, c in enumerate(CONFIGS)}
    results.sort(key=lambda r: (order[r["label"]], r["run"]))
    print("\n| config | run | time s | HTTP | finish | tokens | reasoning chars | JSON | values (verbatim/paraphrase/ungrounded) | invented numbers |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        g = f"{r['values']} ({r['verbatim']}/{r['paraphrase']}/{len(r['ungrounded'])})" if r.get("json") else r.get("error") or f"no JSON: {r.get('content_head', '')!r}"
        print(f"| {r['label']} | {r['run']} | {r['secs']} | {r.get('http')} | {r.get('finish', '')} | {r.get('tokens', '')} | "
              f"{r.get('reasoning_chars', '')} | {'yes' if r.get('json') else 'no'} | {g} | {', '.join(r.get('invented_numbers') or []) or '-'} |")
    print("\nUngrounded values per run:")
    for r in results:
        if r.get("ungrounded"):
            print(f"  {r['label']} run {r['run']}: {'; '.join(r['ungrounded'][:8])}")
    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()

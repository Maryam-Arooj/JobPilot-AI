"""Check the Gemini key: list usable Flash models and time one CV-sized JSON extraction. Never prints the key.

Usage (repo root):  backend\\.venv\\Scripts\\python.exe backend\\scripts\\check_gemini.py
"""
import json
import sys
import time
from pathlib import Path

import requests
from dotenv import dotenv_values

ENV = {k: (v or "").strip() for k, v in dotenv_values(Path(__file__).resolve().parent.parent / ".env").items()}
KEY = ENV.get("GEMINI_API_KEY", "")
BASE = "https://generativelanguage.googleapis.com/v1beta/openai"
if not KEY:
    sys.exit("GEMINI_API_KEY is not set in backend\\.env")
H = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

r = requests.get(f"{BASE}/models", headers=H, timeout=20)
print(f"GET /models -> HTTP {r.status_code}")
if r.status_code != 200:
    sys.exit(r.text[:300].replace(KEY, "<key>"))
ids = sorted(m.get("id", "").replace("models/", "") for m in r.json().get("data", []))
flash = [i for i in ids if "flash" in i and "image" not in i and "tts" not in i and "audio" not in i and "live" not in i]
print("Flash models for this key:", ", ".join(flash[:20]) or "(none)")

model = ENV.get("GEMINI_MODEL") or "gemini-3.8-flash"
if model not in ids:
    print(f"\nNOTE: GEMINI_MODEL={model} is not in the list above. Set GEMINI_MODEL in backend\\.env to one of the Flash models.")
    model = next((m for m in flash if "lite" not in m), flash[0] if flash else model)
cv = ("Jordan Avery\nSenior Data Engineer\njordan@example.com | Austin, TX\nEXPERIENCE\nNorthwind Analytics - Senior Data Engineer "
      "(2021 - Present)\nBuilt Airflow pipelines.\nEDUCATION\nBS Computer Science, UT Austin, 2018\nSKILLS\nPython, SQL, Airflow")
body = {"model": model, "temperature": 0, "max_tokens": 2000, "reasoning_effort": "low", "messages": [
    {"role": "system", "content": "Extract the CV as JSON with keys personal, professional, experience, education, skills. JSON only."},
    {"role": "user", "content": cv}]}
for attempt in range(2):
    t0 = time.time()
    r = requests.post(f"{BASE}/chat/completions", headers=H, json=body, timeout=60)
    dt = time.time() - t0
    if r.status_code == 400 and "reasoning_effort" in body:
        body.pop("reasoning_effort"); continue
    break
print(f"\nTest extraction with {model}: HTTP {r.status_code} in {dt:.1f}s")
if r.ok:
    content = r.json()["choices"][0]["message"]["content"]
    print(content[:600])
    print(f"\nOK: put GEMINI_MODEL={model} in backend\\.env (if not already) and restart the backend.")
else:
    print(r.text[:300].replace(KEY, "<key>"))

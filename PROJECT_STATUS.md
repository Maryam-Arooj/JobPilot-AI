# JobPilot AI — Project Status & Handoff

> **Read this file first.** It is the single source of truth for what this project is, what is done, what is left, and how to continue. Whoever works on the project (human or AI) must update the **Progress log** and the **Task board** after every piece of work.

- **Repository:** https://github.com/Maryam-Arooj/JobPilot-AI (private) — branch `main`
- **Maintainer:** Maryam Arooj
- **Local path (Windows):** `C:\Users\vc\Downloads\jobpilot_AI\jobpilot_AI`
- **Deadline:** project submission ~22 Oct 2026 (3-day sprint: 19–21 Oct)
- **Last updated:** 19 Oct 2026

---

## 1. What we are building

JobPilot AI is a multi-agent career platform. The submission must show **three agents working end-to-end on live APIs with real data**, plus a **live dashboard** that shows what the agents are doing:

| Agent | Job | Live services |
|---|---|---|
| **CV Agent** | Read an uploaded CV (PDF/DOCX/text) → structured career profile (user confirms facts) → tailored resumes in 4 templates (Europass, ATS Clean, Executive Leadership, Technical Specialist) → PDF/DOCX export. | NVIDIA NIM |
| **Job Agent** | Search live jobs for the user's role/location → dedupe → match against confirmed profile with evidence (matched skills, gaps). | SerpAPI Google Jobs, Apify LinkedIn Jobs Scraper, Firecrawl |
| **Email Agent** | Research the company → write an application email grounded in profile + job + research → create a Gmail **draft** (never auto-send). | NVIDIA NIM, SerpAPI, Firecrawl, Gmail API (OAuth) |
| **Live dashboard** | `/agent-transparency` page + Overview card showing each agent's state, runs, steps, tool/API calls, logs and timeline in real time. | Backend `/agent-runs/snapshot` |

Everything else (career counsellor chat, job alerts, career memory, n8n, Docker) is **out of scope** for the submission.

## 2. Non-negotiable rules

1. **Real data only.** Never invent jobs, metrics, CV content, company facts or agent activity. Use honest empty/error states.
2. **Never print, log, store or commit API keys, tokens or `.env` values.** `.env` files are git-ignored and must stay that way.
3. **Do not replace the API keys in `backend/.env`** — they are the owner's originals. Only the login secrets `SECRET_KEY` / `NEXTAUTH_SECRET` may be regenerated.
4. **Do not modify or delete `LICENSE`.** README shows only the maintainer (Maryam Arooj).
5. **Git:** commit as `Maryam Arooj <213998426+Maryam-Arooj@users.noreply.github.com>`. Push only to `origin` (Maryam's repo). Remote `eman` is fetch-only with push disabled — never push there. No force-push.
6. Don't claim a test passed unless it was actually run and the output seen.
7. Keep the UI dark theme (black + raspberry `#ec4c78`, green success, orange-red failure, stone pending; no blue/yellow). Only the CV page itself is white.
8. Work one task at a time; after finishing, update this file, say "Task N done" and ask the owner before starting the next.

## 3. Architecture

- **Frontend:** Next.js 16.3 (App Router, Turbopack), React 19, Tailwind v4 — `frontend/`. NOTE: this Next.js version has breaking changes; see `frontend/AGENTS.md`.
  - Pages: `/` overview, `/profile`, `/confirm`, `/resume`, `/resume-editor`, `/jobs`, `/jobs/[id]`, `/applications`, `/agent-transparency`, `/login`, `/workspace`, `/agent` (out of scope).
  - API client: `frontend/src/lib/api.ts` (`apiFetch`, JWT in localStorage). Shared UI: `frontend/src/components/ui/`.
  - Live dashboard UI: `frontend/src/features/agent-transparency/` — **data contract in `types.ts`** (`AgentSnapshot`, `AgentRun`, `ToolCall`, `LogLine`, `RunEvent`, `RunStep`, `AgentStatus`, `TimelineEvent`). Polls `GET /agent-runs/snapshot?range=1h|24h|7d` every 10 s.
- **Backend:** FastAPI + SQLAlchemy + PostgreSQL 16 — `backend/`. Tables are created at startup (`Base.metadata.create_all`), no Alembic in use.
  - Routers (`backend/api/`): `/auth`, `/profiles`, `/profiles/me/extract`, `/profiles/me/facts`, `/documents`, `/extract`, `/resumes`, `/jobs`, `/applications`, `/companies`, `/gmail`, `/career-memory`, `/job-alerts`.
  - Agents (`backend/ai_agents/`): `profile_agent.py` (CV extraction), `resume_architect.py`, `resume_quality.py`, `job_discovery.py`, `job_analysis.py`, `job_match.py`, `company_research_agent.py`, `application_email_agent.py`. `orchestrator.py` is an 8-line stub.
  - Providers (`backend/providers/`): `serp_job_search.py`, `apify_job_source.py`, `firecrawl_extractor.py`, `company_providers.py`, `email_providers.py` (Gmail drafts), `documents/` parsers.
  - Services (`backend/services/`): `nvidia_llm.py` (typed client: `call_nvidia_llm`, `call_nvidia_json`, `LLMUnavailableError`, `LLMResponseError`, per-model extras), `resume_tailor.py` (grounded tailoring), `resume_exporter.py`, `job_normalizer.py`, `email_service.py` (SMTP, not configured).
  - Scripts: `backend/scripts/check_providers.py` (checks all keys without printing them), `bench_nvidia_extraction.py`.

## 4. How to run (Windows)

```
:: backend
backend\.venv\Scripts\python -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
:: frontend
cd frontend && npm run dev
:: or both
start-servers.bat
:: health
curl http://127.0.0.1:8000/health
:: tests
backend\.venv\Scripts\python -m pytest backend\tests -q
```

- Python 3.13 venv in `backend\.venv` (driver: `psycopg[binary]`). PostgreSQL service `postgresql-x64-16`, database **`jobpilot_v2`** (old `jobpilot` DB has a legacy schema — do not use or modify).
- Test user for demos/screenshots: `demo@jobpilot.local` (fictional profile "Jordan Avery").

### Configuration (names only — never commit values)
`backend/.env`: `DATABASE_URL`, `SECRET_KEY`, `OPENAI_API_KEY` (NVIDIA key), `OPENAI_BASE_URL`, `NVIDIA_MODEL=openai/gpt-oss-20b`, `NVIDIA_FALLBACK_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b`, `NVIDIA_TIMEOUT=45`, `NVIDIA_EXTRA_BODY`, `SERPAPI_KEY`, `SERP_API_KEY`, `APIFY_API_TOKEN`, `APIFY_API_KEY`, `APIFY_ACTOR_ID=curious_coder~linkedin-jobs-scraper`, `FIRECRAWL_API_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI=http://localhost:3000/api/auth/callback/google`.
`frontend/.env`: `NEXT_PUBLIC_API_URL`, `NEXTAUTH_SECRET`, `NEXTAUTH_URL`.

### Provider facts (measured 15 Oct)
- NVIDIA: `openai/gpt-oss-20b` with `reasoning_effort: "low"` ≈ 9–12 s for a CV-sized JSON; fallback nemotron lightning needs `chat_template_kwargs.enable_thinking=false` (`/no_think` does NOT work). Many listed models 404 or time out for this key.
- SerpAPI: free plan, ~230 searches/month left — keep test searches minimal. Backend uses `SERPAPI_KEY` first.
- Apify actor `curious_coder~linkedin-jobs-scraper` input: `keywords`, `location`, `urls`, `limitPerSource`, … (NOT `queries`).
- Firecrawl: ~1000 credits. Google OAuth client valid.

### Working environment notes (for AI assistants)
- The AI assistant works through a Linux sandbox on the owner's PC with this folder mounted. It can edit files, install pip/npm packages and run unit tests (SQLite) and git commit. It **cannot** reach the provider APIs, the Windows Postgres/localhost servers, or push to GitHub — those steps are given to the owner as one command to run, and the output is pasted back.

## 5. Status by area (as of 19 Oct 2026) — overall ≈ 55%

| Area | % | Done | Remaining / known bugs |
|---|---|---|---|
| Foundation | 85 | DB `jobpilot_v2`, auth, typed NVIDIA client, fast model config, provider check, security pass (auth/ownership, no secrets in errors), repo set up | `SECRET_KEY` and `NEXTAUTH_SECRET` are placeholders; hardcoded NextAuth fallback secret in `frontend/src/app/api/auth/[...nextauth]/route.ts` |
| CV Agent | 60 | Upload/parse, Resume Studio, 4 templates, PDF/DOCX export, grounded Tailor Resume (200 in 7–18 s) | Extraction truncated (2000-token cap) → regex fallback **invents** degree/year/experience and saves as **verified**; Edit Profile erases fields not shown (phone); "Save Version" ignores edits; "Sync from Profile" duplicates skills |
| Job Agent | 35 | SerpAPI wired, jobs saved per user, dedupe | SerpAPI returned 0 jobs on 16 Oct (investigate params/location); Apify sends `queries` (wrong) and its error item was saved as a job with 75% match; Firecrawl enrichment is a no-op; matching is keyword-only with invented defaults (score floor 40, 70/75 defaults, "Mid-Senior", "Technology", "BS Computer Science", education always matched) |
| Email Agent | 25 | Gmail draft creation code (real, no fake success), SMTP honest 503 | Emails are fixed templates (no AI) with unsupported claims; company research is **fabricated** (`providers/company_providers.py`) and marked "verified"; company website guessed as `www.<name>.com`; Gmail scope lacks email → address never captured; OAuth `state` = user id; never tested live |
| Live dashboard | 45 | Frontend page complete, honest "Not connected" state | Backend run tracking + `/agent-runs/snapshot` missing; agents not instrumented |
| Overview | 80 | Real data from profile/jobs/resumes/applications/recommendations | No live agent activity card |
| Docs/Repo | 70 | README, 6 new UI screenshots in `docs/screenshots/` | README still has an original-author credit line (line 5) and a "License & Credits" section — owner wants maintainer-only README (keep LICENSE); jobs/applications screenshots missing |

## 6. Task board (3-day sprint)

| # | Task | Day | Status |
|---|---|---|---|
| 1 | **Live dashboard backend:** `AgentRun` model, `track_run` service (own DB session, sanitised, stale-run timeout), `GET /agent-runs/snapshot` + `GET /agent-runs/{id}` matching `types.ts`, instrument CV/Job/Email endpoints, Overview "Live agent activity" card, regenerate login secrets + remove NextAuth fallback. Verify: 1 CV extract + 1 job search shown live. | Mon 19 | ⏳ Not started |
| 2 | **CV Agent:** LLM returns `profile_data` only (facts built in code), 4000 tokens, truncation detection, grounding check (drop values not in source), no example values in prompt, literal-only fallback with `extraction_method`, facts unverified until confirmed, threadpool upload; fix Edit Profile erasure, Save Version, duplicate skills. Verify: grounding table 100%. | Mon 19 | ⏳ Not started |
| 3 | **Job Agent:** debug SerpAPI 0 results, Apify `keywords/location/limitPerSource`, never save error items, parallel providers with timeouts, fix/drop Firecrawl enrichment, LLM job analysis, evidence-based scores, no invented defaults. Verify: 2–3 live searches. | Tue 20 | ⏳ Not started |
| 4 | **Email Agent:** company research = SerpAPI → official site → Firecrawl → LLM summary with sources (empty if nothing); LLM email + claim validator; Gmail `email` scope + signed OAuth state; live draft test. | Tue 20 | ⏳ Not started |
| 5 | **Pipeline:** "Run pipeline" CV → jobs → match → email → Gmail draft, every step visible live on the dashboard. | Wed 21 | ⏳ Not started |
| 6 | **Final:** full test pass, jobs/applications screenshots, maintainer-only README, demo script, push. | Wed 21 | ⏳ Not started |

Status legend: ⏳ not started · 🔄 in progress · ✅ done · ⚠️ blocked

## 7. Progress log (newest first)

- **19 Oct 2026** — Sprint planned (tasks 1–6). Created this file. Overall ≈ 55%.
- **16 Oct 2026** — New README + 6 dark-UI screenshots pushed (`9b18a9d`). Old `Images/` removed. Repo made private. Found bugs: Apify error saved as job, SerpAPI 0 results, Edit Profile erases phone, Save Version ignores edits, duplicate skills.
- **15 Oct 2026** — Repo created under Maryam-Arooj; clean snapshot pushed (`bd5666f`, no history, no keys). Phase 1: new DB `jobpilot_v2`, typed NVIDIA client, fast model (`gpt-oss-20b`, low reasoning), provider check (all keys valid), 56 tests passing (2 environmental failures). Earlier: backend security pass, dark UI redesign, Resume Studio fixes, grounded Tailor Resume.

## 8. Open risks
- SerpAPI free quota (~230 searches) — avoid repeated live searches.
- An old NVIDIA key and one SerpAPI key appear in a public upstream history; owner chose not to rotate. If usage looks unexpected, rotate.
- Live verification depends on the owner running commands on Windows.

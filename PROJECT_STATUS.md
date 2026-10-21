# JobPilot AI — Project Status & Handoff

> **Read this file first.** It is the single source of truth for what this project is, what is done, what is left, and how to continue. Whoever works on the project (human or AI) must update the **Progress log** and the **Task board** after every piece of work.

- **Repository:** https://github.com/Maryam-Arooj/JobPilot-AI (private) — branch `main`
- **Maintainer:** Maryam Arooj
- **Local path (Windows):** `C:\Users\vc\Downloads\jobpilot_AI\jobpilot_AI`
- **Deadline:** project submission ~22 Oct 2026 (3-day sprint: 19–21 Oct)
- **Last updated:** 20 Oct 2026 (Tasks 1–3 done; Task 4 code done, waiting for the owner's live check)

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
5. **Git:** commit as `Maryam Arooj <213998426+Maryam-Arooj@users.noreply.github.com>`. Push only to `origin` (Maryam's repo). Remote `upstream-original` (the original codebase) is fetch-only with push disabled — never push there. No force-push.
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
| Foundation | 90 | DB `jobpilot_v2`, auth, typed NVIDIA client, fast model config, provider check, security pass (auth/ownership, no secrets in errors), repo set up | Login secrets regenerated 19 Oct (users must log in again once); NextAuth fallback secret removed |
| CV Agent | 100 | Grounded extraction (`ai_agents/profile_agent.py`: LLM profile_data only, 4000 tokens, truncation = error, grounding check drops values not in the CV, years from the CV's statement/dates), literal-only fallback (`extraction_method=fallback_partial`), facts saved unverified via `services/profile_ingest.py` (confirmed values never overwritten → conflict), `/documents/parse|upload|sync-profile` + `/profiles/me/extract(/upload)` tracked on the dashboard; Edit Profile merges instead of replacing; Save Version stores the editor content; skills de-duplicated everywhere; sample-CV loader removed from /confirm; Resume Studio, 4 templates, PDF/DOCX, grounded Tailor Resume | Live check on Windows |
| Job Agent | 100 | SerpAPI wired, jobs saved per user, dedupe | SerpAPI returned 0 jobs on 16 Oct (investigate params/location); Apify sends `queries` (wrong) and its error item was saved as a job with 75% match; Firecrawl enrichment is a no-op; matching is keyword-only with invented defaults (score floor 40, 70/75 defaults, "Mid-Senior", "Technology", "BS Computer Science", education always matched) |
| Email Agent | 85 | Company research from the official website only (apply-link domain or SerpAPI Google → Firecrawl → AI summary; every line must be on the page; `not_found`/`unavailable` otherwise), shared service `services/company_research.py` (cached; failed lookups retried after 6 h); AI email from CV + job + research with a fact checker that removes invented numbers, first-person skills not in the CV and company talk without research; honest template fallback; Gmail `openid email` scope, HMAC-signed OAuth state (15 min), draft sent from the connected Gmail; recipient only from the job posting (never guessed); Applications page shows sources and removed claims | Owner live check (`verify_task4.py`) + reconnect Gmail once |
| Live dashboard | 95 | Frontend page; backend run tracking (`AgentRun` model, `services/agent_runs.py`), `GET /agent-runs/snapshot` + `/agent-runs/{id}`; CV/Job/Email endpoints, NVIDIA client, parsers, SerpAPI/Apify/Firecrawl/Gmail calls instrumented; Overview card; 3 s polling while running | Task 5 pipeline view |
| Overview | 90 | Real data from profile/jobs/resumes/applications/recommendations; Live agent activity card (`components/LiveAgentActivity.tsx`) | — |
| Docs/Repo | 70 | README, 6 new UI screenshots in `docs/screenshots/` | README still has an original-author credit line (line 5) and a "License & Credits" section — owner wants maintainer-only README (keep LICENSE); jobs/applications screenshots missing |

## 6. Task board (3-day sprint)

| # | Task | Day | Status |
|---|---|---|---|
| 1 | **Live dashboard backend:** `AgentRun` model, `track_run` service (own DB session, sanitised, stale-run timeout), `GET /agent-runs/snapshot` + `GET /agent-runs/{id}` matching `types.ts`, instrument CV/Job/Email endpoints, Overview "Live agent activity" card, regenerate login secrets + remove NextAuth fallback. Verify: 1 CV extract + 1 job search shown live. | Mon 19 | ✅ Done (owner confirmed live dashboard works, 19 Oct) |
| 2 | **CV Agent:** LLM returns `profile_data` only (facts built in code), 4000 tokens, truncation detection, grounding check (drop values not in source), no example values in prompt, literal-only fallback with `extraction_method`, facts unverified until confirmed, threadpool upload; fix Edit Profile erasure, Save Version, duplicate skills. Verify: grounding table 100%. | Mon 19 | ✅ Done (owner confirmed CV upload works with Gemini, 20 Oct) |
| 3 | **Job Agent:** "Upload your CV → recommended jobs" quick path (search built from the CV's headline, skills and location; works right after /documents/parse or upload); debug SerpAPI 0 results, Apify `keywords/location/limitPerSource`, never save error items, parallel providers with timeouts, fix/drop Firecrawl enrichment, LLM job analysis, evidence-based scores, no invented defaults. Verify: 2–3 live searches. | Tue 20 | ✅ Done (owner confirmed live job search, country + remote, 20 Oct) |
| 4 | **Email Agent:** company research = SerpAPI → official site → Firecrawl → LLM summary with sources (empty if nothing); LLM email + claim validator; Gmail `email` scope + signed OAuth state; live draft test. | Tue 20 | 🔄 Code done 20 Oct, 129 tests pass — waiting for owner live check |
| 5 | **Pipeline:** "Run pipeline" CV → jobs → match → email → Gmail draft, every step visible live on the dashboard. | Wed 21 | ⏳ Not started |
| 6 | **Final:** full test pass, jobs/applications screenshots, maintainer-only README, demo script, push. | Wed 21 | ⏳ Not started |

Status legend: ⏳ not started · 🔄 in progress · ✅ done · ⚠️ blocked

## 7. Progress log (newest first)

- **21 Oct 2026 — Job match bug fixed.** Owner's jobs all said "Your CV covers 0 of N skills; missing: Python" although Python is in the CV: her skills were stored as one JSON text ('["React", "Git", ...]'), so the matcher saw a single skill. `profile_agent.expand_skill_values` now reads lists, JSON text and comma/semicolon/newline text everywhere (`normalize_skills`); `job_matching.candidate_skills` merges `professional.skills` and `skills`; `GET /profiles/me` repairs old text-saved skills in the DB. 137 tests pass. Owner's login account is maryamarooj128x@gmail.com (Gmail for drafts: marycom123x@gmail.com).

- **21 Oct 2026 — CV attaches itself.** Owner's Gmail draft had no CV (application had no linked resume version). `api/applications.py` `resolve_cv`: linked version → newest saved CV version (auto-linked) → PDF built from the saved CV profile. File named `<Name>_CV.pdf`. If the user has no CV at all, the draft is refused with a clear message instead of creating a draft that says "attached" with nothing attached. Exporter now includes Projects (PDF + DOCX). Applications page shows which CV will be attached. 135 tests pass.

- **21 Oct 2026 — Auto recipient.** Owner asked that the To address fills itself. New `POST /applications/{id}/find-recipient`: job-posting emails first, then the company's own /contact, /careers, home, /contact-us, /about pages (Firecrawl, mailto kept), then Google (SerpAPI) — Google results only accepted on the company's own domain. Ranked HR/careers > general; noreply/privacy etc. skipped; cached per company (`CompanyResearchSource` provider `contact_emails`). The draft popup searches automatically, fills the best address, lists the others with their source, has "Search again" and a Connect Gmail button. Never guesses. 132 tests pass.

- **20 Oct 2026 — Task 4 code done.** Rewrote `providers/company_providers.py` (no fabricated text), `ai_agents/company_research_agent.py`, `ai_agents/application_email_agent.py` (AI + fact checker), new `services/company_research.py`, `api/companies.py` (GET never triggers paid research), `api/applications.py` (no guessed website/name/"Technology"; `contact_emails` from posting), `api/gmail.py` (email scope, signed state, token expiry), `providers/email_providers.py` (From = connected Gmail), `frontend/src/app/applications/page.tsx` (no `careers@company.com` guess; sources + removed claims). Tests: `tests/test_email_agent.py` (15). Full suite 129 passed, 2 expected environmental failures (test_jobs_api_phase3, test_phase4_e2e — the latter now correctly gets 0 claims without keys). Live check: `backend/scripts/verify_task4.py`.

- **20 Oct 2026 — Task 3 verified** by the owner: live jobs by CV, country and remote work correctly. Next: Task 4 (Email Agent).
- **20 Oct 2026 — Job search by country + remote (owner feedback).** All jobs were US (Google default) and the country buttons only filtered stored jobs. Now: SerpAPI sends `gl` for the country (pk/us/uk/ca/ae/de…) and uses Google's work-from-home filter (`ltype=1`) for remote; Apify searches `<role> remote` in `Worldwide`. `/jobs/from-cv` `mode`: `auto` = remote (preferred) + the CV's location in parallel, `remote`, `location`. Country buttons on /jobs run a live CV search for that country / remote. Ranking prefers remote within similar scores. Scoring: generic CV words (Development, Software…) are not skills; jobs naming fewer than 4 comparable skills are pulled towards 50 (no 80% for 1 skill). Tests: 115 passed, 2 expected environmental failures.
- **20 Oct 2026 — Task 3 code complete (Job Agent).** Rewrote `providers/serp_job_search.py` (maps real Google Jobs fields: apply_options/share_link, job_highlights → requirements/responsibilities, schedule/salary; retries with the location in the query when Google rejects the location param; no key in errors) and `providers/apify_job_source.py` (input `keywords`/`location`/`limitPerSource`, real LinkedIn field names, error items never become jobs). `ai_agents/job_discovery.py`: both providers in parallel (context-aware threads), no Firecrawl page scraping, per-provider status. `services/job_normalizer.py`: no invented defaults. New `services/job_matching.py`: `score_job` (only skills written in the job; score = share of job skills in the CV + title similarity; None = not enough data; years gap), `analyze_job_with_ai` (Gemini/NVIDIA, grounded in job text). `api/jobs.py`: `/jobs/search` scores results, new `POST /jobs/from-cv` (role + location from the CV, works with an unsaved parsed CV), honest `/jobs/recommendations`, AI `/jobs/{id}/match`. Frontend: "Find Jobs for this CV" passes the parsed CV, Jobs page "Find jobs for my CV" button + banner with provider status, honest score pills. Tests: 110 passed (+13 `tests/test_job_agent.py`), 2 expected environmental failures.
- **20 Oct 2026 — Task 2 verified** by the owner: CV upload (designed PDF) fills the fields quickly and the Gemini-backed refinement works. Next: Task 3 (Job Agent + "upload CV → recommended jobs").
- **20 Oct 2026 — Gemini added as primary AI provider.** NVIDIA free endpoints were too slow (CV refinement 40 s+, vision 120 s timeouts). `services/nvidia_llm.py` now builds ordered targets: Gemini (OpenAI-compatible endpoint, `GEMINI_API_KEY`, `GEMINI_MODEL` default `gemini-3.8-flash`, `GEMINI_TIMEOUT` 40 s, `reasoning_effort` low with automatic retry without it on HTTP 400) first, NVIDIA as automatic fallback (`LLM_PROVIDER=nvidia` reverses). Vision OCR uses Gemini when its key is set. Dashboard tool calls are named `gemini:<model>` / `nvidia:<model>`. Check script: `backend/scripts/check_gemini.py`. Tests: 97 passed, 2 expected environmental failures.
- **19 Oct 2026 (late) — CV reading made fast.** Live run on the owner's designed PDF: NVIDIA vision OCR took 122 s and timed out on page 1, only 73 chars read. Now: PyMuPDF text layer first, then **local OCR (RapidOCR, `pip install rapidocr onnxruntime`)** with column-aware line ordering (`order_ocr_lines`), vision model only as a last resort. New **instant quick read** (`ProfileAgent.quick_extract`, literal section parser: experience/education/projects entries, ~40 ms) answers `/documents/parse` and `/documents/upload` in seconds; the AI extraction runs in the background (`services/cv_refine.py`, `GET /documents/refine/{job_id}`) and the Confirm/Profile pages update by themselves. `?wait=true` keeps the synchronous AI path. Diagnostics: `backend/scripts/show_last_runs.py`, `backend/scripts/test_my_cv.py`. Tests: 93 passed, 2 expected environmental failures.
- **19 Oct 2026 — CV reading for designed/scanned PDFs.** Owner's real CV (designed PDF) gave 0 facts: pdfminer found no text layer. `services/document_service.py` now tries pdfminer → PyMuPDF → NVIDIA vision OCR (`nvidia_llm.call_nvidia_vision_ocr`, model `NVIDIA_VISION_MODEL` default `meta/llama-3.2-11b-vision-instruct`, up to 3 pages, JPEG < 170 KB, 120 s timeout, parallel, tracked on the dashboard); DOCX text boxes/headers read; unreadable files return "" instead of raw bytes. `pymupdf` added to requirements (owner must `pip install pymupdf`). Confirm page upload click fixed (file input was covered by the icon). Owner request for Task 3: after uploading an existing CV, recommend matching jobs directly (quick path without building a new CV). Tests: 88 passed, 2 expected environmental failures.
- **19 Oct 2026 — Task 2 code complete (CV Agent).** Rewrote `backend/ai_agents/profile_agent.py` (grounded LLM extraction + literal fallback, `normalize_skills`/`flatten_skills`), new `backend/services/profile_ingest.py` (`save_extraction`, `filter_confirmed_profile_data`), rewrote `api/documents.py` and `api/profile_extraction.py` (threadpool extraction, 10 MB limit, tracked runs), `nvidia_llm._complete` raises on `finish_reason=length` in JSON mode, `PUT /profiles/me` merges dicts ("" clears), `POST /resumes/{id}/generate` accepts `custom_content` (Save Version), resume_architect dedupes skills. Frontend: /confirm shows extraction method, removed values and missing fields, sample CV loader removed; /profile upload message links to review, links saved under personal, skills deduped; Resume Studio skills deduped. Tests: 85 passed (+14 in `tests/test_cv_agent.py`), 2 expected environmental failures; `tsc` clean. Live check: `backend/scripts/verify_task2.py`.
- **19 Oct 2026 — Task 1 verified** by the owner on Windows: Agent Transparency and Overview show live runs. Task 2 (CV Agent) started.
- **19 Oct 2026 — Task 1 code complete.** Added `backend/models/agent_runs.py` (AgentRun), `backend/services/agent_runs.py` (`track_run`, `tool_call`, `run_log`, `run_warn`, `run_step`; own DB session per write, secret redaction, truncation, 10-min stale timeout), `backend/api/agent_runs.py` (`GET /agent-runs/snapshot?range=1h|24h|7d`, `GET /agent-runs/{id}`, owner-only). Instrumented: `/profiles/me/extract`, `/profiles/me/extract/upload`, `/resumes/{id}/generate`, `/resumes/tailor`, `/jobs/search`, `/jobs/{id}/match`, `/applications/prepare`, `/applications/{id}/generate-email`, `/applications/{id}/gmail-draft`; NVIDIA client (per-model tool calls + fallback warning), document parser, SerpAPI, Apify, Firecrawl (job + company), Gmail drafts/token refresh. Company research placeholder text is now flagged as a warning on the dashboard. Frontend: Overview "Live agent activity" card, dashboard polls every 3 s while a run is active. Regenerated `SECRET_KEY`/`NEXTAUTH_SECRET` (API keys untouched) and removed the hardcoded NextAuth fallback. Tests: 71 passed, 2 expected environmental failures (no job keys in the test copy); frontend `tsc --noEmit` clean. Live check script: `backend/scripts/verify_task1.py`.
- **Test setup for AI assistants:** tests run in an isolated copy on SQLite (`DATABASE_URL=sqlite:///...`, no `.env`). Baseline before Task 1: 56 passed + the same 2 environmental failures. SQLite may log "database is locked" for tracking writes during request transactions; this does not happen on PostgreSQL.
- **19 Oct 2026** — Sprint planned (tasks 1–6). Created this file. Overall ≈ 55%.
- **16 Oct 2026** — New README + 6 dark-UI screenshots pushed (`9b18a9d`). Old `Images/` removed. Repo made private. Found bugs: Apify error saved as job, SerpAPI 0 results, Edit Profile erases phone, Save Version ignores edits, duplicate skills.
- **15 Oct 2026** — Repo created under Maryam-Arooj; clean snapshot pushed (`bd5666f`, no history, no keys). Phase 1: new DB `jobpilot_v2`, typed NVIDIA client, fast model (`gpt-oss-20b`, low reasoning), provider check (all keys valid), 56 tests passing (2 environmental failures). Earlier: backend security pass, dark UI redesign, Resume Studio fixes, grounded Tailor Resume.

## 8. Open risks
- SerpAPI free quota (~230 searches) — avoid repeated live searches.
- An old NVIDIA key and one SerpAPI key appear in a public upstream history; owner chose not to rotate. If usage looks unexpected, rotate.
- Live verification depends on the owner running commands on Windows.

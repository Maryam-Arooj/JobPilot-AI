# JobPilot AI

> A multi-agent career platform that turns your CV into a structured career profile, finds live job openings that match it, and drafts grounded application emails you can send through Gmail.

**Maintained by [Maryam Arooj](https://github.com/Maryam-Arooj)** · Originally created by Eman Yahya · See [License & Credits](#license--credits)

![Overview Dashboard](Images/Overview%20Dashboard.png)

---

## What it does

JobPilot AI is built around three agents that work as one pipeline:

| Agent | What it does | Live services |
|---|---|---|
| **CV Agent** | Reads an uploaded CV (PDF, DOCX or text), extracts a structured career profile, and lets you confirm each fact. Builds tailored resumes in four templates (Europass, ATS Clean, Executive Leadership, Technical Specialist) and exports them to PDF/DOCX. | NVIDIA NIM |
| **Job Agent** | Searches live job listings for your target role and location, removes duplicates, and matches each job against your confirmed skills and experience, showing matched skills and gaps. | SerpAPI (Google Jobs), Apify (LinkedIn), Firecrawl |
| **Email Agent** | Researches the company, drafts an application email grounded in your profile and the job description, and creates a draft in your Gmail account for you to review. It never sends without your confirmation. | NVIDIA NIM, Firecrawl, Gmail API (OAuth) |

**Principle:** the app shows only real data. If a provider fails or returns nothing, you see an honest empty or error state, not invented jobs, metrics or CV content.

## Project status

Active development. Current focus is making the CV, Job and Email agents fully connected to their live APIs:

- [x] Backend security pass (auth and ownership checks, no secrets in error responses)
- [x] Dark UI redesign and Resume Studio with grounded "Tailor Resume"
- [x] Typed NVIDIA client with configurable model, timeout and retries; live provider check script
- [ ] CV Agent: LLM-first extraction, no invented fallback values, user-confirmed facts
- [ ] Job Agent: fixed Apify input, parallel providers, AI job analysis, evidence-based matching
- [ ] Email Agent: real company research, AI-written grounded emails, Gmail draft end-to-end test

## Screenshots

| | |
|---|---|
| ![Resume Studio](Images/Resume%20Studio.png) | ![Job dashboard](Images/Job%20Dashboard%20according%20to%20Cv.png) |
| Resume Studio | Jobs matched to your CV |
| ![Extracted info](Images/Extracted%20Info.png) | ![Recommendations](Images/Recommendations%20of%20jobs%20and%20gaps.png) |
| CV extraction | Matches and skill gaps |

## Tech stack

- **Frontend:** Next.js 16 (App Router, Turbopack), React 19, Tailwind CSS v4
- **Backend:** FastAPI, SQLAlchemy, PostgreSQL 16
- **AI:** NVIDIA NIM (OpenAI-compatible API)
- **Data providers:** SerpAPI Google Jobs, Apify LinkedIn Jobs Scraper, Firecrawl
- **Email:** Gmail API via Google OAuth (drafts only)

## Getting started

### Prerequisites

- Python 3.11+ (tested on 3.13)
- Node.js 20+
- PostgreSQL 16
- API keys: NVIDIA NIM, SerpAPI, Apify, Firecrawl, and a Google OAuth client with the Gmail API enabled

### 1. Clone

```bash
git clone https://github.com/Maryam-Arooj/JobPilot-AI.git
cd JobPilot-AI
```

### 2. Database

Create an empty database (tables are created automatically on first start):

```sql
CREATE DATABASE jobpilot_v2;
```

### 3. Backend

```bash
python -m venv backend/.venv
# Windows: backend\.venv\Scripts\activate    macOS/Linux: source backend/.venv/bin/activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env        # then fill in your values
python backend/scripts/check_providers.py   # optional: checks every key without printing it
uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
```

Check it is running: http://127.0.0.1:8000/health

### 4. Frontend

```bash
cd frontend
npm install
echo NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 > .env
npm run dev
```

Open http://localhost:3000

On Windows you can start both servers with `start-servers.bat`.

## Configuration

`backend/.env`:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | e.g. `postgresql://postgres:<password>@localhost:5432/jobpilot_v2` |
| `SECRET_KEY` | Long random string used to sign login tokens. Never use the placeholder. |
| `OPENAI_API_KEY` | NVIDIA NIM API key |
| `OPENAI_BASE_URL` | `https://integrate.api.nvidia.com/v1` |
| `NVIDIA_MODEL`, `NVIDIA_FALLBACK_MODEL` | Model ids used by the agents |
| `NVIDIA_TIMEOUT`, `NVIDIA_EXTRA_BODY` | Request timeout in seconds; optional per-model request options |
| `SERPAPI_KEY` | SerpAPI key for Google Jobs |
| `APIFY_API_TOKEN`, `APIFY_ACTOR_ID` | Apify token and LinkedIn jobs actor |
| `FIRECRAWL_API_KEY` | Firecrawl key for job pages and company research |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` | Gmail OAuth; redirect is `http://localhost:3000/api/auth/callback/google` |

`frontend/.env`: `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000`

> Never commit `.env` files. They are listed in `.gitignore`.

## Project structure

```
backend/
  ai_agents/     profile (CV), job discovery, job analysis/match, email, company research
  api/           FastAPI routers: auth, profiles, resumes, jobs, applications, gmail
  providers/     SerpAPI, Apify, Firecrawl, Gmail, document parsers
  services/      NVIDIA client, resume tailoring/export, job normalisation
  scripts/       provider and model checks
  tests/
frontend/
  src/app/       pages: overview, profile, resume studio, jobs, applications
  src/components/ shared UI
docs/            architecture notes
```

## Running tests

```bash
cd backend
python -m pytest
```

## License & Credits

JobPilot AI was **originally created by Eman Yahya**, who holds the copyright to the original code. This repository is **maintained and extended by Maryam Arooj** with her permission; Maryam Arooj holds the copyright to her own contributions and changes.

Copyright © 2026 Eman Yahya (original code) · Copyright © 2026 Maryam Arooj (contributions). All rights reserved. See [LICENSE](LICENSE) for the full terms, including the original author's preserved notice.

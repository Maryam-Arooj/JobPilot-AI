# JobPilot AI — START SERVER GUIDE (Windows CMD)

> **Complete Step-by-Step Guide to Setup, Start, Test, and Troubleshoot JobPilot AI Servers**

---

## 1. Verified Project Location & Navigation

**Verified Absolute Directory:** `c:\Users\vc\Downloads\jobpilot_AI\jobpilot_AI`

To begin, open your Windows Command Prompt (**CMD**) and navigate to the project root folder:

```cmd
REM Open Windows CMD and navigate to the verified project root path
cd /d "c:\Users\vc\Downloads\jobpilot_AI\jobpilot_AI"
```

---

## 2. Fast 1-Click Launch (All-in-One)

If environment setup and dependencies are already completed, you can start both Backend and Frontend servers simultaneously with a single command:

```cmd
REM Launch Backend (Port 8000) and Frontend (Port 3000) in separate CMD windows
cd /d "c:\Users\vc\Downloads\jobpilot_AI\jobpilot_AI"
start-servers.bat
```

---

## 3. Manual Server Startup Guide

For initial setup, debugging, or running components independently, follow these step-by-step instructions across separate terminals.

### 🗄️ Optional Prerequisite: PostgreSQL Database Service

JobPilot AI uses PostgreSQL (Port 5432). If you prefer running PostgreSQL via Docker:

```cmd
REM Start PostgreSQL 16 Alpine container in background
cd /d "c:\Users\vc\Downloads\jobpilot_AI\jobpilot_AI"
docker-compose up -d postgres
```

---

### 🐍 Backend Server — Terminal 1 (FastAPI + Uvicorn)

Open **Terminal 1** and run the following commands:

```cmd
REM Step 1: Open project root folder
cd /d "c:\Users\vc\Downloads\jobpilot_AI\jobpilot_AI"

REM Step 2: Activate Python Virtual Environment (if configured)
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat

REM Step 3: Verify and install Python backend dependencies (if needed)
pip install -r backend/requirements.txt

REM Step 4: Run database schema migrations (if using PostgreSQL)
alembic upgrade head

REM Step 5: Start FastAPI Backend Server with Uvicorn live reload
python -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000 --reload
```

* **Backend Base URL:** `http://127.0.0.1:8000`
* **Swagger API Interactive Docs:** `http://127.0.0.1:8000/docs`
* **ReDoc API Documentation:** `http://127.0.0.1:8000/redoc`
* **Health Check Endpoint:** `http://127.0.0.1:8000/health`
* **Stop Backend Server:** Press `Ctrl + C` inside Terminal 1.

---

### ⚛️ Frontend Server — Terminal 2 (Next.js 16 + React 19)

Open **Terminal 2** and run the following commands:

```cmd
REM Step 1: Open frontend folder
cd /d "c:\Users\vc\Downloads\jobpilot_AI\jobpilot_AI\frontend"

REM Step 2: Verify Node.js and NPM versions (Node.js v18+ or v20+ required)
node -v
npm -v

REM Step 3: Install frontend dependencies (if not already installed)
npm install

REM Step 4: Start Next.js Development Server
npm run dev
```

* **Frontend Application URL:** `http://localhost:3000`
* **Stop Frontend Server:** Press `Ctrl + C` inside Terminal 2.

---

## 4. Execution Order & Service Architecture

To ensure smooth inter-service communication, start the services in the following order:

```
┌──────────────────────────────────────────────────────────┐
│  Step 1: PostgreSQL Database (Local / Docker Port 5432)  │
└────────────────────────────┬─────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────┐
│  Step 2: FastAPI Backend Server (Terminal 1 - Port 8000) │
└────────────────────────────┬─────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────┐
│  Step 3: Next.js Frontend App (Terminal 2 - Port 3000)   │
└──────────────────────────────────────────────────────────┘
```

---

## 5. End-to-End Automated Testing Commands

To run all verified backend end-to-end integration and unit tests:

```cmd
REM Navigate to root directory
cd /d "c:\Users\vc\Downloads\jobpilot_AI\jobpilot_AI"

REM Activate Virtual Environment
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat

REM Run complete Pytest test suite (25 E2E tests)
python -m pytest backend/tests
```

To run individual phase test flows:

```cmd
REM Phase 1 E2E (Auth & Profile Sync)
python -m pytest backend/tests/test_e2e_phase1_flow.py

REM Phase 2 E2E (Resume Studio & Multi-Format Exports)
python -m pytest backend/tests/test_resume_phase2.py

REM Phase 3 E2E (Job Discovery Engine & Match Matrix)
python -m pytest backend/tests/test_jobs_api_phase3.py

REM Phase 4 E2E (Application CRM & Gmail Outreach)
python -m pytest backend/tests/test_phase4_e2e.py
```

---

## 6. Troubleshooting & Common Fixes

### Issue 1: Port Already in Use (Port 8000 or 3000)
If port 8000 or 3000 is occupied by a background process, run these CMD commands to identify and release the port:

```cmd
REM Check process occupying Port 8000 (Backend)
netstat -ano | findstr :8000
REM Kill process using its PID (Replace <PID> with actual process ID number)
taskkill /PID <PID> /F

REM Check process occupying Port 3000 (Frontend)
netstat -ano | findstr :3000
taskkill /PID <PID> /F
```

### Issue 2: Missing Python Dependencies or ModuleNotFoundError
Ensure you are using the correct Python environment and re-install dependencies:

```cmd
cd /d "c:\Users\vc\Downloads\jobpilot_AI\jobpilot_AI"
pip install -r backend/requirements.txt
```

### Issue 3: Missing `.env` Configuration File
If environment variables are missing, create `.env` from `.env.example`:

```cmd
cd /d "c:\Users\vc\Downloads\jobpilot_AI\jobpilot_AI"
if not exist .env copy .env.example .env
if not exist backend\.env copy .env.example backend\.env
```

### Issue 4: Frontend Cannot Connect to Backend (CORS / Connection Refused)
1. Verify Backend is running on `http://127.0.0.1:8000`.
2. Ensure `frontend\.env` contains:
   ```env
   NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
   ```
3. Restart Frontend (`npm run dev`).

### Issue 5: Google OAuth "Error 403: access_denied" (App in Testing Mode)
If Google displays *`JobPilot AI has not completed the Google verification process... Error 403: access_denied`*:
1. Open [Google Cloud Console OAuth Consent Screen](https://console.cloud.google.com/apis/credentials/consent).
2. Under **Test users**, click **+ ADD USERS**.
3. Add your Gmail address (e.g. `yourname@gmail.com`) and click **Save**.
4. Retry clicking **Connect Gmail** in JobPilot AI.

---

## 7. Configuration Quick Reference

| Component | Port / Path | Purpose |
| :--- | :--- | :--- |
| **Frontend App** | `http://localhost:3000` | Next.js 16 UI Dashboard & Resume Studio |
| **Backend API** | `http://127.0.0.1:8000` | FastAPI Multi-Agent Engine & Data Endpoints |
| **Swagger Docs** | `http://127.0.0.1:8000/docs` | Interactive REST API Endpoint Documentation |
| **PostgreSQL DB** | `localhost:5432` | Canonical Database Storage |

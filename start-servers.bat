@echo off
start "Backend (JobPilot AI)" cmd /k "cd /d "%~dp0" && backend\.venv\Scripts\python.exe -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000"
start "Frontend (JobPilot AI)" cmd /k "cd /d "%~dp0frontend" && npm run dev"

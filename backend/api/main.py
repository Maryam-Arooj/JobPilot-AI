import os
from pathlib import Path
# Load .env before any other imports so providers get real API keys
_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(str(_env_file))
    except ImportError:
        # If python-dotenv not installed, manually parse
        for line in _env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ..db.database import Base, engine
from .. import models  # noqa: F401

Base.metadata.create_all(bind=engine)

from .profiles import router as profiles_router
from .extraction import router as extraction_router
from .auth import router as auth_router
from .documents import router as documents_router
from .profile_facts import router as facts_router
from .profile_extraction import router as profile_extraction_router
from .conflict_resolution import router as conflict_router
from .resumes import router as resumes_router
from .jobs import router as jobs_router
from .applications import router as applications_router
from .companies import router as companies_router
from .gmail import router as gmail_router
from .career_memory import router as career_memory_router
from .job_alerts import router as job_alerts_router

app = FastAPI(title="JobPilot AI / YourCareer Buddy API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "*"
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profiles_router)
app.include_router(extraction_router)
app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(facts_router)
app.include_router(profile_extraction_router)
app.include_router(conflict_router)
app.include_router(resumes_router)
app.include_router(jobs_router)
app.include_router(companies_router)
app.include_router(applications_router)
app.include_router(gmail_router)
app.include_router(career_memory_router)
app.include_router(job_alerts_router)

@app.get("/health")
def health():
    return {"status": "ok"}


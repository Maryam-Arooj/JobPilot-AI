from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..services import pipeline
from ..services.auth_middleware import get_current_user_id

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


class PipelineRequest(BaseModel):
    location: Optional[str] = None      # e.g. "Pakistan"; default = the CV's location
    mode: str = "auto"                   # auto = remote + location, remote, location
    require_email: bool = True           # only finish with a job that has a real recruiter email
    max_jobs: int = 10


@router.post("/apply")
def start_pipeline(req: PipelineRequest, user_id: int = Depends(get_current_user_id)):
    mode = req.mode if req.mode in ("auto", "remote", "location") else "auto"
    return {"pipeline_id": pipeline.start(user_id, req.location, mode, req.require_email, max(1, min(req.max_jobs, 15)))}


@router.get("/{pipeline_id}")
def pipeline_status(pipeline_id: str, user_id: int = Depends(get_current_user_id)):
    p = pipeline.get(pipeline_id, user_id)
    if not p:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return p

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..ai_agents.profile_agent import ProfileAgent
from ..db.database import get_db
from ..services.agent_runs import track_run
from ..services.auth_middleware import get_current_user_id
from ..services.document_service import extract_text_and_profile
from ..services.profile_ingest import save_extraction
from .documents import _read_upload

router = APIRouter(prefix="/profiles/me/extract", tags=["profile_extraction"])
agent = ProfileAgent()


class ExtractIn(BaseModel):
    text: str
    auto_save: bool = True


def _response(extracted, result=None, **extra):
    body = {
        "status": "success",
        "facts": result["facts"] if result else extracted.get("facts", []),
        "profile_data": extracted.get("profile_data", {}),
        "missing_fields": extracted.get("missing_fields", []),
        "followup_questions": extracted.get("followup_questions", []),
        "extraction_method": extracted.get("extraction_method"),
        "dropped": extracted.get("dropped", []),
        "message": extracted.get("message", ""),
        "saved_to_profile": result is not None,
    }
    if result:
        body.update({"needs_review": result["needs_review"], "conflicts": result["conflicts"],
                     "completeness_pct": result["profile"].completeness_pct})
    body.update(extra)
    return body


@router.post("")
def extract_profile(data: ExtractIn, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    """Extract a grounded career profile from pasted CV/bio text. Saved facts need the user's review."""
    with track_run(user_id, "cv", "Extract career profile from text",
                   input_summary={"text_chars": len(data.text or ""), "auto_save": data.auto_save}) as run:
        run.step("AI extraction and grounding check", 1, 2)
        extracted = agent.extract_from_text(data.text)
        result = None
        if data.auto_save and extracted.get("profile_data"):
            run.step("Save profile (facts need your review)", 2, 2)
            result = save_extraction(db, user_id, extracted, source="text_extraction")
            db.commit()
        run.set_output({"extraction_method": extracted.get("extraction_method"), "facts": len(extracted.get("facts", [])),
                        "dropped_values": len(extracted.get("dropped", [])), "saved_to_profile": result is not None,
                        "missing_fields": extracted.get("missing_fields", [])})
        return _response(extracted, result)


@router.post("/upload")
async def upload_cv_document(file: UploadFile = File(...), user_id: int = Depends(get_current_user_id),
                             db: Session = Depends(get_db)):
    """Upload a CV (.pdf, .docx, .txt), extract a grounded profile and save it for review."""
    filename = file.filename or "cv.pdf"
    with track_run(user_id, "cv", f"Extract career profile from {filename}",
                   input_summary={"filename": filename, "content_type": file.content_type}) as run:
        run.step("Read document", 1, 3)
        content = await _read_upload(file)
        run.step("AI extraction and grounding check", 2, 3)
        _, extracted = await run_in_threadpool(extract_text_and_profile, content, filename)
        run.step("Save profile (facts need your review)", 3, 3)
        result = save_extraction(db, user_id, extracted, source="cv_upload")
        db.commit()
        run.set_output({"extraction_method": extracted.get("extraction_method"), "facts": len(result["facts"]),
                        "needs_review": result["needs_review"], "conflicts": result["conflicts"]})
        return _response(extracted, result, filename=filename)

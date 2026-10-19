import re
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from ..db.database import get_db
from ..models.resume import ResumeDocument, ResumeVersion, ResumeQualityReport
from ..models.career_profile import CareerProfile, ProfileFact
from ..models.jobs import Job
from ..schemas.resume import ResumeCreate, ResumeGenerate, ResumeUpdate, ResumeTailorRequest
from ..services.auth_middleware import get_current_user_id
from ..services.resume_tailor import tailor_cv, TailorUnavailable
from ..services.agent_runs import track_run
from .jobs import _user_job_ids
from ..ai_agents.resume_architect import ResumeArchitect
from ..ai_agents.resume_quality import ResumeQualityAgent
from ..services.resume_renderer import ResumeRenderer
from ..services.resume_exporter import ResumeExporter

router = APIRouter(prefix="/resumes", tags=["resumes"])

def get_user_profile(db: Session, user_id: int):
    profile = db.query(CareerProfile).filter(CareerProfile.user_id == user_id).first()
    if not profile:
        raise HTTPException(
            status_code=404,
            detail="Career profile not found. Please complete your profile at /profile first."
        )
    return profile

def _serialize_resume(resume: ResumeDocument, latest_version: ResumeVersion = None) -> dict:
    return {
        "id": resume.id,
        "title": resume.title,
        "template": resume.template,
        "target_role": resume.target_role,
        "approved": resume.approved,
        "created_at": str(resume.created_at) if hasattr(resume, 'created_at') and resume.created_at else None,
        "latest_version_id": latest_version.id if latest_version else None,
        "latest_version_number": latest_version.version_number if latest_version else None,
        "content_snapshot": latest_version.content_snapshot if latest_version else None,
    }

@router.post("/")
def create_resume(data: ResumeCreate, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    profile = get_user_profile(db, user_id)
    resume = ResumeDocument(
        user_id=user_id,
        career_profile_id=profile.id,
        template=data.template,
        target_role=data.target_role,
        title=data.title or f"{data.target_role or 'Resume'} — {data.template}"
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return _serialize_resume(resume)

@router.get("/")
def list_resumes(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    resumes = db.query(ResumeDocument).filter(ResumeDocument.user_id == user_id).all()
    result = []
    for r in resumes:
        latest = (
            db.query(ResumeVersion)
            .filter(ResumeVersion.resume_id == r.id)
            .order_by(ResumeVersion.version_number.desc())
            .first()
        )
        result.append(_serialize_resume(r, latest))
    return result

@router.get("/{resume_id}")
def get_resume(resume_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    resume = db.query(ResumeDocument).filter(
        ResumeDocument.id == resume_id,
        ResumeDocument.user_id == user_id
    ).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    latest = (
        db.query(ResumeVersion)
        .filter(ResumeVersion.resume_id == resume.id)
        .order_by(ResumeVersion.version_number.desc())
        .first()
    )
    return _serialize_resume(resume, latest)

@router.post("/{resume_id}/generate")
def generate_resume(
    resume_id: int,
    data: ResumeGenerate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    with track_run(user_id, "cv", f"Generate resume #{resume_id}", input_summary={"resume_id": resume_id, "template": data.template, "target_role": data.target_role}) as run:
        resume = db.query(ResumeDocument).filter(
            ResumeDocument.id == resume_id,
            ResumeDocument.user_id == user_id
        ).first()
        if not resume:
            raise HTTPException(status_code=404, detail="Resume not found")

        target_role = data.target_role or resume.target_role
        template = data.template or resume.template
        custom = data.custom_content or {}
        has_custom = any(custom.get(k) for k in ("summary", "experience", "education", "skills", "name", "title"))
        if has_custom:
            # Save Version: keep exactly what the user edited in Resume Studio.
            run.step("Save edited resume", 1, 1)
            doc = {**custom, "template": template, "target_role": target_role, "source": "resume_studio_edit"}
            doc.pop("custom_content", None)
            latest = (db.query(ResumeVersion).filter(ResumeVersion.resume_id == resume.id)
                      .order_by(ResumeVersion.version_number.desc()).first())
            next_version = (latest.version_number + 1) if latest else 1
            version = ResumeVersion(resume_id=resume.id, version_number=next_version, target_role=target_role,
                                    content_snapshot=doc, source_profile_version="editor", status="draft")
            db.add(version)
            resume.approved = True
            resume.template = template
            if target_role:
                resume.target_role = target_role
            db.commit()
            db.refresh(version)
            run.set_output({"version_number": next_version, "template": template, "source": "editor"})
            return {"version_id": version.id, "version_number": next_version, "content_snapshot": doc,
                    "template": template, "target_role": target_role}

        profile = db.query(CareerProfile).filter(CareerProfile.id == resume.career_profile_id).first()
        if not profile:
            raise HTTPException(status_code=404, detail="Career profile not found")

        # Check profile has at least some data
        has_data = (
            profile.personal or profile.professional or profile.experience or
            profile.education or profile.skills
        )
        if not has_data:
            raise HTTPException(
                status_code=400,
                detail="Career profile is empty. Please fill in your profile information at /profile before generating a resume."
            )

        run.step("Build resume from profile", 1, 2)
        architect = ResumeArchitect()
        target_role = data.target_role or resume.target_role
        template = data.template or resume.template

        doc = architect.build(
            {
                "personal": profile.personal or {},
                "professional": profile.professional or {},
                "education": profile.education or [],
                "experience": profile.experience or [],
                "skills": profile.skills or {},
                "projects": profile.projects or [],
                "certifications": profile.certifications or [],
                "achievements": profile.achievements or [],
                "publications": profile.publications or [],
                "portfolio": profile.portfolio or [],
            },
            target_role=target_role,
            template=template,
        )

        run.step("Save version", 2, 2)
        # Version management
        latest = (
            db.query(ResumeVersion)
            .filter(ResumeVersion.resume_id == resume.id)
            .order_by(ResumeVersion.version_number.desc())
            .first()
        )
        next_version = (latest.version_number + 1) if latest else 1

        version = ResumeVersion(
            resume_id=resume.id,
            version_number=next_version,
            target_role=target_role,
            content_snapshot=doc,
            source_profile_version="v1",
            status="draft",
        )
        db.add(version)

        # Auto-approve after generation so export works immediately
        resume.approved = True
        resume.template = template
        if target_role:
            resume.target_role = target_role

        db.commit()
        db.refresh(version)
        run.set_output({"version_number": next_version, "template": template, "sections": len([k for k, v in doc.items() if v])})
        return {
            "version_id": version.id,
            "version_number": next_version,
            "content_snapshot": doc,
            "template": template,
            "target_role": target_role,
        }

@router.post("/{resume_id}/quality-check")
def quality_check(resume_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    resume = db.query(ResumeDocument).filter(
        ResumeDocument.id == resume_id,
        ResumeDocument.user_id == user_id
    ).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    version = (
        db.query(ResumeVersion)
        .filter(ResumeVersion.resume_id == resume.id)
        .order_by(ResumeVersion.version_number.desc())
        .first()
    )
    if not version:
        raise HTTPException(status_code=404, detail="No version generated yet")

    profile = db.query(CareerProfile).filter(CareerProfile.id == resume.career_profile_id).first()
    agent = ResumeQualityAgent()
    report = agent.check(
        version.content_snapshot,
        {
            "personal": profile.personal or {},
            "professional": profile.professional or {},
        },
        resume.template,
    )
    qr = ResumeQualityReport(
        version_id=version.id,
        status=report["status"],
        issues=report["issues"],
        warnings=report["warnings"],
        suggestions=report["suggestions"],
    )
    db.add(qr)
    db.commit()
    return report

@router.post("/{resume_id}/approve")
def approve_resume(resume_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    resume = db.query(ResumeDocument).filter(
        ResumeDocument.id == resume_id,
        ResumeDocument.user_id == user_id
    ).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    resume.approved = True
    db.commit()
    return {"approved": True}

@router.post("/tailor")
def tailor_resume(req: ResumeTailorRequest, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    """Grounded AI tailoring of the editor's current CV. Returns proposals only; nothing is saved."""
    with track_run(user_id, "cv", f"Tailor resume for {req.target_role or 'target role'}", input_summary={"target_role": req.target_role, "job_id": req.job_id, "job_description_chars": len(req.job_description or "")}) as run:
        cv = req.cv.model_dump()
        if not (cv["summary"].strip() or cv["experience"] or cv["skills"]):
            raise HTTPException(status_code=400, detail="Add a summary, experience or skills to your CV before tailoring it.")

        job_description = req.job_description or ""
        if req.job_id is not None:
            job = db.query(Job).filter(Job.id == req.job_id).first() if req.job_id in _user_job_ids(db, user_id) else None
            if not job:
                raise HTTPException(status_code=404, detail="Job not found")
            parts = [job.title, job.company, job.description,
                     "Requirements: " + ", ".join(map(str, job.requirements or [])),
                     "Technologies: " + ", ".join(map(str, job.technologies or [])),
                     job_description]
            job_description = "\n".join(p for p in parts if p)

        facts = [
            {"path": f.path, "value": f.value}
            for f in db.query(ProfileFact)
            .join(CareerProfile, CareerProfile.id == ProfileFact.profile_id)
            .filter(CareerProfile.user_id == user_id, ProfileFact.verified == True)  # noqa: E712
            .all()
        ]

        run.step("AI tailoring (grounded)", 1, 1)
        run.log("info", f"{len(facts)} verified profile facts used for grounding")
        try:
            result = tailor_cv(req.target_role, cv, job_description, facts)
            if isinstance(result, dict):
                run.set_output({k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in result.items() if k != "cv"})
            return result
        except TailorUnavailable as e:
            reason = ("returned a response that could not be used" if str(e) == "invalid"
                      else "could not be reached")
            raise HTTPException(
                status_code=503,
                detail=f"AI tailoring is unavailable: the language model {reason}. Your CV was not changed. Please try again later."
            )

def _export_or_500(export_fn, content: Dict[str, Any]) -> bytes:
    try:
        return export_fn(content)
    except Exception:
        # Exporter logs the traceback server-side
        raise HTTPException(status_code=500, detail="Resume export failed")

@router.post("/export-preview-pdf")
def export_preview_pdf(payload: Dict[str, Any], user_id: int = Depends(get_current_user_id)):
    """
    Directly export any active resume form data into a pristine A4 Europass PDF document.
    Does not require database lookup or stored version so user can export live edits instantly.
    """
    pdf_bytes = _export_or_500(ResumeExporter().export_pdf, payload)
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', str(payload.get("name") or "Curriculum_Vitae"))
    filename = f"{safe_name}_Europass_CV.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )

@router.get("/{resume_id}/export/pdf")
@router.post("/{resume_id}/export/pdf")
def export_pdf(resume_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    resume = db.query(ResumeDocument).filter(
        ResumeDocument.id == resume_id,
        ResumeDocument.user_id == user_id
    ).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    version = (
        db.query(ResumeVersion)
        .filter(ResumeVersion.resume_id == resume.id)
        .order_by(ResumeVersion.version_number.desc())
        .first()
    )
    if not version or not version.content_snapshot:
        raise HTTPException(
            status_code=400,
            detail="No generated content found. Please generate a resume version first using the Generate button."
        )

    renderer = ResumeRenderer(resume.template)
    exporter = ResumeExporter(renderer)
    pdf_bytes = _export_or_500(exporter.export_pdf, version.content_snapshot)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=resume_{resume_id}.pdf"},
    )

@router.get("/{resume_id}/export/docx")
@router.post("/{resume_id}/export/docx")
def export_docx(resume_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    resume = db.query(ResumeDocument).filter(
        ResumeDocument.id == resume_id,
        ResumeDocument.user_id == user_id
    ).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    version = (
        db.query(ResumeVersion)
        .filter(ResumeVersion.resume_id == resume.id)
        .order_by(ResumeVersion.version_number.desc())
        .first()
    )
    if not version or not version.content_snapshot:
        raise HTTPException(
            status_code=400,
            detail="No generated content found. Please generate a resume version first using the Generate button."
        )

    renderer = ResumeRenderer(resume.template)
    exporter = ResumeExporter(renderer)
    docx_bytes = _export_or_500(exporter.export_docx, version.content_snapshot)
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename=resume_{resume_id}.docx"},
    )

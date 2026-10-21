import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from ..db.database import get_db
from ..models.applications import Application, ApplicationEvent, ApplicationEmailVersion, EmailDraft, GmailConnection
from ..models.jobs import Job, JobMatch
from ..models.companies import Company, CompanyResearch
from ..models.career_profile import CareerProfile, User
from ..models.resume import ResumeVersion, ResumeDocument
from ..services.auth_middleware import get_current_user_id
from ..ai_agents.application_email_agent import ApplicationEmailAgent
from ..providers.email_providers import GmailEmailProvider, GmailNotConnectedError, GmailDraftError
from ..services.email_service import EmailSenderService, SMTPNotConfiguredError, SMTPDeliveryError
from ..services.resume_exporter import export_resume_pdf, export_resume_docx
from ..services.agent_runs import track_run
from ..services import company_research as cr

router = APIRouter(prefix="/applications", tags=["applications"])

def _owned_version(db: Session, version_id: Optional[int], user_id: int) -> Optional[ResumeVersion]:
    if not version_id:
        return None
    return (db.query(ResumeVersion).join(ResumeDocument, ResumeDocument.id == ResumeVersion.resume_id)
            .filter(ResumeVersion.id == version_id, ResumeDocument.user_id == user_id).first())


def _latest_version(db: Session, user_id: int) -> Optional[ResumeVersion]:
    return (db.query(ResumeVersion).join(ResumeDocument, ResumeDocument.id == ResumeVersion.resume_id)
            .filter(ResumeDocument.user_id == user_id).order_by(ResumeVersion.id.desc()).first())


def resolve_cv(db: Session, app_obj: Application, user_id: int, link: bool = False) -> Dict[str, Any]:
    """Which CV goes with this application: linked version -> newest saved version -> the CV profile itself."""
    rv = _owned_version(db, app_obj.resume_version_id, user_id)
    if rv and rv.content_snapshot:
        return {"source": "resume_version", "version_id": rv.id, "content": rv.content_snapshot,
                "label": f"Saved CV version #{rv.id}"}
    rv = _latest_version(db, user_id)
    if rv and rv.content_snapshot:
        if link:
            app_obj.resume_version_id = rv.id
        return {"source": "resume_version", "version_id": rv.id, "content": rv.content_snapshot,
                "label": f"Your newest saved CV (version #{rv.id})"}
    prof = _profile_dict(db, user_id)
    has_cv = (prof["personal"].get("name") or prof["personal"].get("full_name")) and \
        (prof["experience"] or prof["education"] or prof["skills"] or prof["projects"])
    if has_cv:
        return {"source": "profile", "version_id": None, "content": prof, "label": "CV built from your saved profile"}
    return {"source": None, "version_id": None, "content": None, "label": ""}


def _build_resume_attachment(db: Session, app_obj: Application, user_id: int, fmt: str, base_name: str = "CV"):
    """Export the CV for this application. Always the user's own data."""
    cv = resolve_cv(db, app_obj, user_id, link=True)
    if not cv["content"]:
        return None, None, cv
    personal = cv["content"].get("personal") or cv["content"].get("header") or {}
    name = (personal.get("name") or personal.get("full_name") or cv["content"].get("name") or "").strip()
    safe = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
    fname = f"{safe}_CV" if safe else base_name
    try:
        if fmt.lower() == "docx":
            return export_resume_docx(cv["content"]), f"{fname}.docx", cv
        return export_resume_pdf(cv["content"]), f"{fname}.pdf", cv
    except Exception:
        raise HTTPException(status_code=500, detail="Your CV could not be turned into a PDF. Try DOCX or save a CV version first.")


from ..services.recipients import EMAIL_RE, contact_emails, linkedin_url as _linkedin_url, search_recipients


def _profile_dict(db: Session, user_id: int) -> Dict[str, Any]:
    """The user's real profile. The name is never guessed from the email address."""
    user_record = db.query(User).filter(User.id == user_id).first()
    profile = db.query(CareerProfile).filter(CareerProfile.user_id == user_id).first()
    personal = dict(profile.personal or {}) if (profile and profile.personal) else {}
    if not personal.get("email") and user_record:
        personal["email"] = user_record.email
    return {
        "personal": personal,
        "professional": (profile.professional or {}) if profile else {},
        "skills": (profile.skills or {}) if profile else {},
        "experience": (profile.experience or []) if profile else [],
        "projects": (profile.projects or []) if profile else [],
        "education": (profile.education or []) if profile else [],
    }


def _job_dict(job: Job) -> Dict[str, Any]:
    return {"title": job.title, "company": job.company, "location": job.location, "description": job.description,
            "requirements": job.requirements or [], "technologies": job.technologies or []}


def _write_email(db: Session, run, app_obj: Application, job: Job, comp: Optional[Company], tone: str) -> Dict[str, Any]:
    profile_dict = _profile_dict(db, app_obj.user_id)
    research = cr.payload(db, comp, cr.latest(db, comp.id)) if comp else {}
    if research.get("status") != "found":
        run.log("info", research.get("message") or "No company research; the email uses only the CV and the job.")
    email_res = ApplicationEmailAgent().generate_email(career_profile=profile_dict, job=_job_dict(job),
                                                       company_research=research, tone=tone)
    db.add(ApplicationEmailVersion(
        application_id=app_obj.id, tone=email_res["tone"], subject=email_res["subject"], body=email_res["body"],
        greeting=email_res["greeting"], closing=email_res["closing"],
        referenced_profile_facts=email_res["referenced_profile_facts"],
        referenced_job_requirements=email_res["referenced_job_requirements"],
        referenced_company_claims=email_res["referenced_company_claims"]))
    return email_res

class ApplicationCreate(BaseModel):
    job_id: int
    company_id: Optional[int] = None
    resume_version_id: Optional[int] = None

class EmailGenerateRequest(BaseModel):
    tone: str = "Formal"
    resume_version_id: Optional[int] = None

class EmailUpdateRequest(BaseModel):
    subject: str
    body: str
    tone: Optional[str] = "Formal"

class GmailDraftRequest(BaseModel):
    recipient: str
    subject: str
    body: str
    user_confirmed: bool = False
    include_attachment: bool = True
    attachment_format: str = "pdf"  # pdf or docx

@router.post("")
@router.post("/")
@router.post("/prepare")
def create_application(
    req: ApplicationCreate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    with track_run(user_id, "email", f"Prepare application for job #{req.job_id}", input_summary={"job_id": req.job_id, "resume_version_id": req.resume_version_id}) as run:
        job = db.query(Job).filter(Job.id == req.job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        comp = (db.query(Company).filter(Company.id == req.company_id).first() if req.company_id
                else cr.get_or_create_company(db, job))
        company_id = comp.id if comp else None

        run.step("Company research", 1, 3)
        try:
            rec = cr.research_and_save(db, comp, job.application_url or job.source_url,
                                       trusted_website=cr.linkedin_facts(db, job).get("company_website") or None) if comp else None
            research_status = cr.payload(db, comp, rec)["status"] if comp else "not_researched"
        except Exception as e:
            run.warn(f"Company research failed: {e}")
            research_status = "unavailable"

        run.step("Create application workspace", 2, 3)
        # 2. Create Application Record
        app_obj = Application(
            user_id=user_id,
            job_id=req.job_id,
            company_id=company_id,
            resume_version_id=(req.resume_version_id if _owned_version(db, req.resume_version_id, user_id) else
                               (getattr(_latest_version(db, user_id), "id", None))),
            status="DRAFT_READY"
        )
        db.add(app_obj)
        db.flush()

        db.add(ApplicationEvent(
            application_id=app_obj.id,
            event_type="APPLICATION_CREATED",
            description=f"Application workspace created for {job.title} at {job.company}"
        ))

        run.step("Draft application email", 3, 3)
        try:
            email_res = _write_email(db, run, app_obj, job, comp, "Formal")
        except Exception as e:
            run.warn(f"Email drafting failed: {e}")
            email_res = {}

        db.commit()
        run.set_output({"application_id": app_obj.id, "job": f"{job.title} at {job.company}",
                        "company_research": research_status, "email_method": email_res.get("method"),
                        "removed_claims": len(email_res.get("removed_claims") or [])})
        return get_application(app_obj.id, user_id, db)

@router.get("")
@router.get("/")
def list_applications(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    apps = db.query(Application).filter(Application.user_id == user_id).order_by(Application.id.desc()).all()
    res = []
    for a in apps:
        job = db.query(Job).filter(Job.id == a.job_id).first()
        comp = db.query(Company).filter(Company.id == a.company_id).first() if a.company_id else None
        res.append({
            "id": a.id,
            "job_id": a.job_id,
            "job_title": job.title if job else "Unknown Job",
            "company_name": comp.name if comp else (job.company if job else "Unknown Company"),
            "status": a.status,
            "created_at": a.created_at
        })
    return res

@router.get("/{app_id}")
def get_application(
    app_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    app_obj = db.query(Application).filter(Application.id == app_id, Application.user_id == user_id).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail="Application workspace not found")

    job = db.query(Job).filter(Job.id == app_obj.job_id).first()
    comp = db.query(Company).filter(Company.id == app_obj.company_id).first() if app_obj.company_id else None
    
    research = cr.payload(db, comp, cr.latest(db, comp.id)) if comp else None

    # Load latest email version
    latest_email = db.query(ApplicationEmailVersion).filter(ApplicationEmailVersion.application_id == app_id).order_by(ApplicationEmailVersion.id.desc()).first()
    
    # Load latest draft confirmation
    latest_draft = db.query(EmailDraft).filter(EmailDraft.application_id == app_id).order_by(EmailDraft.id.desc()).first()

    return {
        "id": app_obj.id,
        "user_id": app_obj.user_id,
        "status": app_obj.status,
        "job": {
            "id": job.id if job else None,
            "title": job.title if job else "Position",
            "company": job.company if job else "Company",
            "location": job.location if job else "",
            "remote": job.remote if job else False,
            "salary": job.salary if job else None,
            "application_url": job.application_url if job else "",
            "contact_emails": contact_emails(job)
        },
        "contacts": ([{"email": e, "kind": "job_posting", "source_url": job.application_url or job.source_url or ""}
                      for e in contact_emails(job)] + (cr.cached_contacts(db, comp) or [])) if job else [],
        "company": {
            "id": comp.id if comp else None,
            "name": comp.name if comp else (job.company if job else "Company"),
            "official_website": (comp.official_website or "") if comp else "",
            "research": research
        },
        "resume_version_id": app_obj.resume_version_id,
        "cv_attachment": {k: v for k, v in resolve_cv(db, app_obj, user_id).items() if k != "content"},
        "email_version": {
            "tone": latest_email.tone,
            "subject": latest_email.subject,
            "body": latest_email.body,
            "greeting": latest_email.greeting,
            "closing": latest_email.closing,
            "referenced_profile_facts": latest_email.referenced_profile_facts,
            "referenced_job_requirements": latest_email.referenced_job_requirements,
            "referenced_company_claims": latest_email.referenced_company_claims
        } if latest_email else None,
        "gmail_draft": {
            "draft_id": latest_draft.draft_id,
            "recipient": latest_draft.recipient,
            "subject": latest_draft.subject,
            "created_at": latest_draft.created_at
        } if latest_draft else None
    }

@router.post("/{app_id}/generate-email")
def generate_application_email(
    app_id: int,
    req: EmailGenerateRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    with track_run(user_id, "email", f"Generate {req.tone} application email", input_summary={"application_id": app_id, "tone": req.tone}) as run:
        app_obj = db.query(Application).filter(Application.id == app_id, Application.user_id == user_id).first()
        if not app_obj:
            raise HTTPException(status_code=404, detail="Application workspace not found")

        if req.resume_version_id:
            app_obj.resume_version_id = req.resume_version_id

        job = db.query(Job).filter(Job.id == app_obj.job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        comp = db.query(Company).filter(Company.id == app_obj.company_id).first() if app_obj.company_id else None

        run.step("Load company research", 1, 2)
        if comp and cr.latest(db, comp.id) is None:
            try:
                cr.research_and_save(db, comp, job.application_url or job.source_url,
                                     trusted_website=cr.linkedin_facts(db, job).get("company_website") or None)
            except Exception as e:
                run.warn(f"Company research failed: {e}")

        run.step("Write and fact-check email", 2, 2)
        email_res = _write_email(db, run, app_obj, job, comp, req.tone)

        app_obj.status = "DRAFT_READY"
        db.add(ApplicationEvent(
            application_id=app_id,
            event_type="EMAIL_GENERATED",
            description=f"Generated {req.tone} application email draft"
        ))
        db.commit()
        run.set_output({"subject": email_res.get("subject"), "tone": email_res.get("tone"),
                        "method": email_res.get("method"), "removed_claims": len(email_res.get("removed_claims") or []),
                        "body_chars": len(email_res.get("body", ""))})
        return email_res

@router.get("/{app_id}/email")
def get_application_email(
    app_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    app_obj = db.query(Application).filter(Application.id == app_id, Application.user_id == user_id).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail="Application workspace not found")

    email_ver = db.query(ApplicationEmailVersion).filter(ApplicationEmailVersion.application_id == app_id).order_by(ApplicationEmailVersion.id.desc()).first()
    if not email_ver:
        raise HTTPException(status_code=404, detail="No email generated for this application yet")

    return {
        "tone": email_ver.tone,
        "subject": email_ver.subject,
        "body": email_ver.body,
        "greeting": email_ver.greeting,
        "closing": email_ver.closing,
        "referenced_profile_facts": email_ver.referenced_profile_facts,
        "referenced_job_requirements": email_ver.referenced_job_requirements,
        "referenced_company_claims": email_ver.referenced_company_claims
    }

@router.put("/{app_id}/email")
def update_application_email(
    app_id: int,
    req: EmailUpdateRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    app_obj = db.query(Application).filter(Application.id == app_id, Application.user_id == user_id).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail="Application workspace not found")

    email_ver = db.query(ApplicationEmailVersion).filter(ApplicationEmailVersion.application_id == app_id).order_by(ApplicationEmailVersion.id.desc()).first()
    if not email_ver:
        email_ver = ApplicationEmailVersion(
            application_id=app_id,
            tone=req.tone or "Formal",
            subject=req.subject,
            body=req.body
        )
        db.add(email_ver)
    else:
        email_ver.subject = req.subject
        email_ver.body = req.body
        if req.tone:
            email_ver.tone = req.tone

    app_obj.status = "READY_FOR_REVIEW"
    db.add(ApplicationEvent(
        application_id=app_id,
        event_type="EMAIL_EDITED",
        description="User edited application email subject/body"
    ))
    db.commit()

    return {
        "status": "success",
        "subject": email_ver.subject,
        "body": email_ver.body,
        "tone": email_ver.tone
    }

@router.post("/{app_id}/find-recipient")
def find_recipient(app_id: int, force: bool = False, user_id: int = Depends(get_current_user_id),
                   db: Session = Depends(get_db)):
    """Find a REAL recipient: posting, job pages, public LinkedIn posts, the company's site and the web."""
    app_obj = db.query(Application).filter(Application.id == app_id, Application.user_id == user_id).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail="Application workspace not found")
    job = db.query(Job).filter(Job.id == app_obj.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    comp = db.query(Company).filter(Company.id == app_obj.company_id).first() if app_obj.company_id else None
    if contact_emails(job) and not force:
        return search_recipients(db, job, comp)
    with track_run(user_id, "email", f"Find recipient email for {comp.name if comp else job.company}",
                   input_summary={"application_id": app_id}) as run:
        run.step("Search job pages, LinkedIn posts, company website and the web", 1, 1)
        out = search_recipients(db, job, comp, force=force)
        run.set_output({"found": len(out["contacts"]), "cached": out.get("cached"),
                        "domains": sorted({c["email"].split("@")[1] for c in out["contacts"]})})
        return out


@router.post("/{app_id}/gmail-draft")
def create_gmail_draft(
    app_id: int,
    req: GmailDraftRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    with track_run(user_id, "email", "Create Gmail draft", input_summary={"application_id": app_id, "recipient_domain": (req.recipient.split("@")[-1] if "@" in (req.recipient or "") else None), "attachment": req.include_attachment}) as run:
        # MANDATORY SAFETY & HUMAN APPROVAL CHECK
        if not req.user_confirmed:
            raise HTTPException(status_code=400, detail="Explicit user approval (user_confirmed=True) is mandatory before creating Gmail draft")

        if not req.recipient or not EMAIL_RE.fullmatch(req.recipient.strip()):
            raise HTTPException(status_code=400, detail="Valid recipient email address is required")

        app_obj = db.query(Application).filter(Application.id == app_id, Application.user_id == user_id).first()
        if not app_obj:
            raise HTTPException(status_code=404, detail="Application workspace not found")

        run.step("Prepare resume attachment", 1, 2)
        # Export selected resume attachment if requested
        attachment_bytes, attachment_name = None, None
        if req.include_attachment:
            attachment_bytes, attachment_name, cv = _build_resume_attachment(db, app_obj, user_id, req.attachment_format)
            if not attachment_bytes:
                raise HTTPException(status_code=400, detail="No CV found to attach. Upload your CV on the Confirm page "
                                    "(or untick 'Attach CV'). No draft was created.")
            run.log("info", f"Attached {attachment_name} ({cv['label']})")

        sender_email = None  # the draft is created in, and sent from, the connected Gmail account

        run.step("Create draft in Gmail", 2, 2)
        provider = GmailEmailProvider()
        try:
            draft_res = provider.create_draft(
                user_id=user_id,
                recipient=req.recipient,
                subject=req.subject,
                body=req.body,
                attachment_bytes=attachment_bytes,
                attachment_filename=attachment_name,
                sender_email=sender_email,
                db_session=db
            )
        except GmailNotConnectedError:
            raise HTTPException(
                status_code=409,
                detail="Gmail is not connected. Connect your Gmail account before creating a draft. No draft was created."
            )
        except GmailDraftError:
            raise HTTPException(
                status_code=502,
                detail="Gmail rejected or failed the draft request. No draft was created. Try reconnecting Gmail."
            )

        draft_record = EmailDraft(
            application_id=app_id,
            provider=draft_res["provider"],
            draft_id=draft_res["draft_id"],
            recipient=req.recipient,
            subject=req.subject,
            body=req.body,
            has_attachment=bool(attachment_bytes),
            attachment_name=attachment_name
        )
        db.add(draft_record)

        app_obj.status = "DRAFT_READY"
        db.add(ApplicationEvent(
            application_id=app_id,
            event_type="GMAIL_DRAFT_CREATED",
            description=f"Gmail draft {draft_record.draft_id} created for recipient {req.recipient}"
        ))
        db.commit()
        run.set_output({"draft_created": True, "has_attachment": bool(attachment_bytes), "attachment": attachment_name})
        return {
            "status": "success",
            "draft_id": draft_record.draft_id,
            "recipient": draft_record.recipient,
            "subject": draft_record.subject,
            "has_attachment": draft_record.has_attachment,
            "attachment_name": draft_record.attachment_name,
            "message": "Gmail draft created successfully. The email has NOT been sent and is saved in your Gmail Drafts folder."
        }

def _send_or_raise(**kwargs) -> Dict[str, Any]:
    try:
        return EmailSenderService().send_email(**kwargs)
    except ValueError:
        raise HTTPException(status_code=400, detail="Valid recipient email address is required")
    except SMTPNotConfiguredError:
        raise HTTPException(
            status_code=503,
            detail="Email sending is not configured on the server (SMTP). The email was NOT sent."
        )
    except SMTPDeliveryError:
        raise HTTPException(status_code=502, detail="Email delivery failed. The email was NOT sent.")

class DirectEmailSendRequest(BaseModel):
    recipient: str
    subject: str
    body: str
    include_attachment: bool = True
    attachment_format: str = "pdf"

@router.post("/{app_id}/send-email")
def send_application_email(
    app_id: int,
    req: DirectEmailSendRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Direct in-code email delivery (No n8n dependency). Dispatches email to recipient
    with generated PDF/DOCX resume attached.
    """
    app_obj = db.query(Application).filter(Application.id == app_id, Application.user_id == user_id).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail="Application workspace not found")

    attachment_bytes, attachment_name = None, None
    if req.include_attachment:
        attachment_bytes, attachment_name, _cv = _build_resume_attachment(db, app_obj, user_id, req.attachment_format)

    result = _send_or_raise(
        to_email=req.recipient,
        subject=req.subject,
        body=req.body,
        attachment_bytes=attachment_bytes,
        attachment_filename=attachment_name
    )

    # Only reached when SMTP actually accepted the message
    app_obj.status = "SUBMITTED"
    db.add(ApplicationEvent(
        application_id=app_id,
        event_type="EMAIL_SENT_DIRECT",
        description=f"Application email dispatched directly in code to {req.recipient}"
    ))
    db.commit()

    return {
        "status": "success",
        "delivery": result,
        "application_status": "SUBMITTED"
    }

@router.post("/send-direct-email")
def send_direct_email(
    req: DirectEmailSendRequest,
    user_id: int = Depends(get_current_user_id)
):
    """
    Standalone direct email dispatch in code.
    """
    result = _send_or_raise(
        to_email=req.recipient,
        subject=req.subject,
        body=req.body
    )
    return {
        "status": "success",
        "delivery": result
    }


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
from ..ai_agents.company_research_agent import CompanyResearchAgent
from ..ai_agents.job_analysis import JobAnalysisAgent
from ..ai_agents.job_match import JobMatchAgent
from ..providers.email_providers import GmailEmailProvider, GmailNotConnectedError, GmailDraftError
from ..services.email_service import EmailSenderService, SMTPNotConfiguredError, SMTPDeliveryError
from ..services.resume_exporter import export_resume_pdf, export_resume_docx

router = APIRouter(prefix="/applications", tags=["applications"])

def _build_resume_attachment(db: Session, app_obj: Application, user_id: int, fmt: str, base_name: str):
    """Export the application's resume version, only if it belongs to the current user."""
    if not app_obj.resume_version_id:
        return None, None
    rv = (
        db.query(ResumeVersion)
        .join(ResumeDocument, ResumeDocument.id == ResumeVersion.resume_id)
        .filter(ResumeVersion.id == app_obj.resume_version_id, ResumeDocument.user_id == user_id)
        .first()
    )
    if not rv or not rv.content_snapshot:
        return None, None
    try:
        if fmt.lower() == "pdf":
            return export_resume_pdf(rv.content_snapshot), f"{base_name}.pdf"
        return export_resume_docx(rv.content_snapshot), f"{base_name}.docx"
    except Exception:
        raise HTTPException(status_code=500, detail="Resume attachment could not be generated")

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
    job = db.query(Job).filter(Job.id == req.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    company_id = req.company_id
    company_name = (job.company or "Technology Organization").strip()
    if not company_id:
        comp = db.query(Company).filter(Company.name == company_name).first()
        if not comp:
            comp = Company(
                name=company_name,
                official_website=job.source_url or f"https://www.{company_name.lower().replace(' ', '')}.com"
            )
            db.add(comp)
            db.flush()
        company_id = comp.id
    else:
        comp = db.query(Company).filter(Company.id == company_id).first()

    # 1. Autonomous Company Research
    res_record = db.query(CompanyResearch).filter(CompanyResearch.company_id == company_id).order_by(CompanyResearch.id.desc()).first()
    company_research_dict = {}
    if not res_record and comp:
        try:
            comp_agent = CompanyResearchAgent()
            res_data = comp_agent.research(
                company_name=comp.name,
                official_website=comp.official_website,
                job_url=job.source_url or job.application_url
            )
            res_record = CompanyResearch(
                company_id=comp.id,
                overview=res_data.get("overview"),
                products_services=res_data.get("products_services", []),
                technology_info=res_data.get("technology_info", []),
                engineering_info=res_data.get("engineering_info", ""),
                mission_info=res_data.get("mission_info", ""),
                recent_news=res_data.get("recent_news", []),
                careers_url=res_data.get("careers_url", ""),
                confidence_status="verified"
            )
            db.add(res_record)
            db.flush()
            company_research_dict = {
                "company_name": comp.name,
                "overview": res_record.overview,
                "industry": comp.industry or "Technology",
                "technology_info": res_record.technology_info or [],
                "mission_info": res_record.mission_info or ""
            }
        except Exception as e:
            print(f"Company research notice: {e}")
    elif res_record and comp:
        company_research_dict = {
            "company_name": comp.name,
            "overview": res_record.overview,
            "industry": comp.industry or "Technology",
            "technology_info": res_record.technology_info or [],
            "mission_info": res_record.mission_info or ""
        }

    # 2. Create Application Record
    app_obj = Application(
        user_id=user_id,
        job_id=req.job_id,
        company_id=company_id,
        resume_version_id=req.resume_version_id,
        status="DRAFT_READY"
    )
    db.add(app_obj)
    db.flush()

    db.add(ApplicationEvent(
        application_id=app_obj.id,
        event_type="APPLICATION_CREATED",
        description=f"Application workspace created for {job.title} at {job.company}"
    ))

    # 3. Autonomous Grounded Email Drafting based on Company Research & Job Match
    try:
        user_record = db.query(User).filter(User.id == user_id).first()
        profile = db.query(CareerProfile).filter(CareerProfile.user_id == user_id).first()
        
        user_account_email = user_record.email if user_record else ""
        personal_data = dict(profile.personal or {}) if (profile and profile.personal) else {}
        personal_data["email"] = user_account_email or personal_data.get("email", "")
        if not personal_data.get("name"):
            personal_data["name"] = user_account_email.split("@")[0].replace(".", " ").capitalize() if user_account_email else "Applicant"

        profile_dict = {
            "personal": personal_data,
            "professional": profile.professional or {} if profile else {},
            "skills": profile.skills or {} if profile else {},
            "experience": profile.experience or [] if profile else []
        }

        job_dict = {
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "description": job.description
        }

        analysis_agent = JobAnalysisAgent()
        job_analysis = analysis_agent.analyze({"requirements": job.requirements, "technologies": job.technologies})

        match_agent = JobMatchAgent()
        job_match = match_agent.match(profile_dict, job_dict, job_analysis)

        email_agent = ApplicationEmailAgent()
        email_res = email_agent.generate_email(
            career_profile=profile_dict,
            job=job_dict,
            job_analysis=job_analysis,
            job_match=job_match,
            company_research=company_research_dict,
            resume_version={},
            tone="Formal"
        )

        email_ver = ApplicationEmailVersion(
            application_id=app_obj.id,
            tone=email_res.get("tone", "Formal"),
            subject=email_res.get("subject", f"Application for {job.title} - {profile_dict.get('personal', {}).get('name', 'Alex Chen')}"),
            body=email_res.get("body", ""),
            greeting=email_res.get("greeting", "Dear Hiring Team,"),
            closing=email_res.get("closing", "Sincerely,"),
            referenced_profile_facts=email_res.get("referenced_profile_facts", []),
            referenced_job_requirements=email_res.get("referenced_job_requirements", []),
            referenced_company_claims=email_res.get("referenced_company_claims", [])
        )
        db.add(email_ver)
    except Exception as e:
        print(f"Auto email drafting notice: {e}")

    db.commit()
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
    
    # Load company research if present
    research = None
    if comp:
        research_record = db.query(CompanyResearch).filter(CompanyResearch.company_id == comp.id).order_by(CompanyResearch.id.desc()).first()
        if research_record:
            research = {
                "overview": research_record.overview,
                "industry": comp.industry or "Technology",
                "products_services": research_record.products_services,
                "technology_info": research_record.technology_info,
                "mission_info": research_record.mission_info,
                "careers_url": research_record.careers_url
            }

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
            "application_url": job.application_url if job else ""
        },
        "company": {
            "id": comp.id if comp else None,
            "name": comp.name if comp else (job.company if job else "Company"),
            "official_website": comp.official_website if comp else "",
            "research": research
        },
        "resume_version_id": app_obj.resume_version_id,
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
    app_obj = db.query(Application).filter(Application.id == app_id, Application.user_id == user_id).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail="Application workspace not found")

    if req.resume_version_id:
        app_obj.resume_version_id = req.resume_version_id

    # Load canonical facts
    user_record = db.query(User).filter(User.id == user_id).first()
    profile = db.query(CareerProfile).filter(CareerProfile.user_id == user_id).first()
    
    user_account_email = user_record.email if user_record else ""
    personal_data = dict(profile.personal or {}) if (profile and profile.personal) else {}
    personal_data["email"] = user_account_email or personal_data.get("email", "")
    if not personal_data.get("name"):
        personal_data["name"] = user_account_email.split("@")[0].replace(".", " ").capitalize() if user_account_email else "Applicant"

    profile_dict = {
        "personal": personal_data,
        "professional": profile.professional or {} if profile else {},
        "skills": profile.skills or {} if profile else {},
        "experience": profile.experience or [] if profile else []
    }

    job = db.query(Job).filter(Job.id == app_obj.job_id).first()
    job_dict = {
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "description": job.description
    }

    # Job analysis & match
    analysis_agent = JobAnalysisAgent()
    job_analysis = analysis_agent.analyze({"requirements": job.requirements, "technologies": job.technologies})

    match_agent = JobMatchAgent()
    job_match = match_agent.match(profile_dict, job_dict, job_analysis)

    # Company research
    company_research = {}
    if app_obj.company_id:
        res_record = db.query(CompanyResearch).filter(CompanyResearch.company_id == app_obj.company_id).order_by(CompanyResearch.id.desc()).first()
        if res_record:
            company_research = {
                "company_name": job.company,
                "industry": "Technology",
                "technology_info": res_record.technology_info or []
            }
        else:
            comp_agent = CompanyResearchAgent()
            res_data = comp_agent.research(job.company)
            company_research = {
                "company_name": job.company,
                "industry": res_data.get("industry", "Technology"),
                "technology_info": res_data.get("technology_info", [])
            }

    email_agent = ApplicationEmailAgent()
    email_res = email_agent.generate_email(
        career_profile=profile_dict,
        job=job_dict,
        job_analysis=job_analysis,
        job_match=job_match,
        company_research=company_research,
        resume_version={},
        tone=req.tone
    )

    email_ver = ApplicationEmailVersion(
        application_id=app_id,
        tone=email_res["tone"],
        subject=email_res["subject"],
        body=email_res["body"],
        greeting=email_res["greeting"],
        closing=email_res["closing"],
        referenced_profile_facts=email_res["referenced_profile_facts"],
        referenced_job_requirements=email_res["referenced_job_requirements"],
        referenced_company_claims=email_res["referenced_company_claims"]
    )
    db.add(email_ver)

    app_obj.status = "DRAFT_READY"
    db.add(ApplicationEvent(
        application_id=app_id,
        event_type="EMAIL_GENERATED",
        description=f"Generated {req.tone} application email draft"
    ))
    db.commit()

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

@router.post("/{app_id}/gmail-draft")
def create_gmail_draft(
    app_id: int,
    req: GmailDraftRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    # MANDATORY SAFETY & HUMAN APPROVAL CHECK
    if not req.user_confirmed:
        raise HTTPException(status_code=400, detail="Explicit user approval (user_confirmed=True) is mandatory before creating Gmail draft")

    if not req.recipient or "@" not in req.recipient:
        raise HTTPException(status_code=400, detail="Valid recipient email address is required")

    app_obj = db.query(Application).filter(Application.id == app_id, Application.user_id == user_id).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail="Application workspace not found")

    # Export selected resume attachment if requested
    attachment_bytes, attachment_name = None, None
    if req.include_attachment:
        attachment_bytes, attachment_name = _build_resume_attachment(db, app_obj, user_id, req.attachment_format, "Resume")

    user = db.query(User).filter(User.id == user_id).first()
    sender_email = user.email if user else "applicant@yourcareerbuddy.com"

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
        attachment_bytes, attachment_name = _build_resume_attachment(db, app_obj, user_id, req.attachment_format, "Application_Resume")

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


"""Task 4 — Email Agent: real company research, grounded + fact-checked email, honest Gmail draft flow."""
import sys
import uuid
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from fastapi.testclient import TestClient

from backend.ai_agents.application_email_agent import ApplicationEmailAgent
from backend.api import gmail as gmail_api
from backend.api.applications import contact_emails
from backend.api.main import app
from backend.db.database import SessionLocal
from backend.models.career_profile import CareerProfile, User
from backend.models.jobs import Job
from backend.providers import company_providers as cp
from backend.services.auth_service import create_token

client = TestClient(app)

PROFILE = {
    "personal": {"name": "Jordan Avery", "email": "jordan@example.org"},
    "professional": {"headline": "Data Engineer", "skills": ["Python", "SQL", "Airflow"]},
    "skills": {"technical": ["Python", "SQL", "Airflow"]},
    "experience": [{"title": "Data Engineer", "company": "Northwind", "start_date": "2022", "end_date": "Present"}],
    "projects": [{"name": "Sales Pipeline", "description": "Airflow pipeline for daily sales data"}],
}
JOB = {"title": "Data Engineer", "company": "Acme Analytics",
       "description": "We need Python, SQL and Airflow. Kafka is a plus.", "requirements": ["Python", "SQL"]}
RESEARCH = {"status": "found", "overview": "Acme Analytics builds reporting software for retailers.",
            "products_services": ["Acme Insights"], "technology_info": [], "mission_info": "", "claims": [{"claim_text": "x"}]}
PAGE = ("# Acme Analytics\nAcme Analytics builds reporting software for retailers. Our product Acme Insights helps "
        "store managers see sales in real time. We use Python and PostgreSQL. " * 3)


def _resp(status, data):
    r = mock.Mock(status_code=status)
    r.json.return_value = data
    return r


# ---------------- official website ----------------
def test_job_boards_are_never_the_official_site():
    assert not cp._is_official_candidate("https://www.linkedin.com/company/acme")
    assert not cp._is_official_candidate("https://boards.greenhouse.io/acme/jobs/1")
    assert cp._is_official_candidate("https://acmeanalytics.com")
    assert cp._domain_matches_company("https://careers.acmeanalytics.com/x", "Acme Analytics Pvt Ltd")
    assert not cp._domain_matches_company("https://randomblog.com", "Acme Analytics")
    assert cp._root("https://careers.acmeanalytics.com/jobs/1") == "https://acmeanalytics.com"


def test_website_from_apply_link_needs_no_search(monkeypatch):
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    p = cp.FirecrawlCompanyResearchProvider(api_key="k")
    site, how = p.find_official_website("Acme Analytics", "https://jobs.acmeanalytics.com/123")
    assert site == "https://acmeanalytics.com" and "apply link" in how


def test_website_from_google_skips_job_boards(monkeypatch):
    monkeypatch.setenv("SERPAPI_KEY", "s")
    p = cp.FirecrawlCompanyResearchProvider(api_key="k")
    data = {"organic_results": [{"link": "https://www.linkedin.com/company/acme-analytics"},
                                {"link": "https://www.glassdoor.com/acme"}, {"link": "https://www.acmeanalytics.io/about"}]}
    with mock.patch.object(cp.requests, "get", return_value=_resp(200, data)):
        site, _ = p.find_official_website("Acme Analytics", "https://www.linkedin.com/jobs/view/1")
    assert site == "https://acmeanalytics.io"


def test_no_website_means_no_company_facts(monkeypatch):
    monkeypatch.setenv("SERPAPI_KEY", "s")
    p = cp.FirecrawlCompanyResearchProvider(api_key="k")
    with mock.patch.object(cp.requests, "get", return_value=_resp(200, {"organic_results": [{"link": "https://indeed.com/x"}]})):
        out = p.research_company("Acme Analytics")
    assert out["status"] == "not_found" and out["claims"] == [] and out["overview"] == "" and out["industry"] == ""


def test_summary_keeps_only_facts_on_the_page(monkeypatch):
    p = cp.FirecrawlCompanyResearchProvider(api_key="k")
    ai = {"overview": "Acme Analytics builds reporting software for retailers.", "industry": "Fintech",
          "products_services": ["Acme Insights", "Acme Rocket Launcher"], "technology_info": ["Python", "Kubernetes"],
          "mission_info": "To colonise Mars by 2030."}
    with mock.patch("backend.services.nvidia_llm.call_nvidia_json", return_value=ai):
        out = p.summarize("Acme Analytics", PAGE)
    assert out["overview"].startswith("Acme Analytics builds")
    assert out["industry"] == ""                       # "Fintech" is not on the page
    assert out["products_services"] == ["Acme Insights"]
    assert out["technology_info"] == ["Python"]
    assert out["mission_info"] == ""


def test_full_research_with_sources(monkeypatch):
    p = cp.FirecrawlCompanyResearchProvider(api_key="k")
    ai = {"overview": "Acme Analytics builds reporting software for retailers.", "products_services": ["Acme Insights"]}
    with mock.patch.object(cp.requests, "post", return_value=_resp(200, {"data": {"markdown": PAGE}})), \
         mock.patch("backend.services.nvidia_llm.call_nvidia_json", return_value=ai):
        out = p.research_company("Acme Analytics", job_url="https://acmeanalytics.com/careers/1")
    assert out["status"] == "found" and out["official_website"] == "https://acmeanalytics.com"
    assert out["sources"][0]["source_url"] == "https://acmeanalytics.com"
    assert {c["fact_type"] for c in out["claims"]} == {"overview", "product"}


# ---------------- email ----------------
def test_checker_removes_invented_numbers_and_skills():
    agent = ApplicationEmailAgent()
    f = agent.facts(PROFILE, JOB, RESEARCH)
    body = ("I have used Python and SQL at Northwind. I have 7 years of experience. "
            "I also built systems with Kubernetes. I improved speed by 40%. I am excited about Acme Insights.")
    text, removed = agent.check(body, f)
    assert "Python and SQL" in text and "Acme Insights" in text
    assert "7 years" not in text and "Kubernetes" not in text and "40%" not in text
    assert len(removed) == 3


def test_checker_blocks_company_talk_without_research():
    agent = ApplicationEmailAgent()
    f = agent.facts(PROFILE, JOB, {"status": "not_found"})
    text, removed = agent.check("I love your mission and products. I use Python.", f)
    assert "mission" not in text and "Python" in text and removed


def test_ai_email_is_fact_checked():
    fake = {"subject": "Data Engineer application - Jordan Avery",
            "body": "I am applying for the Data Engineer role. I have 9 years of Spark experience. I use Python and Airflow."}
    with mock.patch("backend.services.nvidia_llm.call_nvidia_json", return_value=fake):
        out = ApplicationEmailAgent().generate_email(PROFILE, JOB, company_research=RESEARCH, tone="Technical")
    assert out["method"] == "ai"
    assert "9 years" not in out["body"] and "Python and Airflow" in out["body"]
    assert out["removed_claims"] and out["body"].startswith("Dear Acme Analytics Hiring Team,")
    assert out["closing"].endswith("jordan@example.org")


def test_template_when_ai_down_has_no_invented_claims():
    from backend.services.nvidia_llm import LLMUnavailableError
    with mock.patch("backend.services.nvidia_llm.call_nvidia_json", side_effect=LLMUnavailableError("down")):
        out = ApplicationEmailAgent().generate_email(PROFILE, JOB, company_research={"status": "not_found"})
    body = out["body"].lower()
    assert out["method"] == "template"
    for bad in ("verified", "technology sector", "alex chen", "scalable", "immediate value"):
        assert bad not in body
    assert "python" in body and "northwind" in body and "sales pipeline" in body


# ---------------- gmail + recipient ----------------
def test_oauth_state_is_signed_and_expires():
    st = gmail_api.make_state(42, now=1000)
    assert gmail_api.read_state(st, now=1001) == 42
    with pytest.raises(Exception):
        gmail_api.read_state(st, now=1000 + gmail_api.STATE_TTL + 1)
    with pytest.raises(Exception):
        gmail_api.read_state("42")                     # old unsigned style is rejected


def test_oauth_url_asks_for_email_scope(monkeypatch):
    monkeypatch.setattr(gmail_api, "GOOGLE_CLIENT_ID", "cid")
    db = SessionLocal()
    u = User(email=f"g-{uuid.uuid4().hex[:6]}@test.local", password_hash="x"); db.add(u); db.commit(); db.refresh(u)
    uid = u.id
    db.close()
    r = client.get("/gmail/oauth/start", headers={"Authorization": f"Bearer {create_token(uid)}"})
    url = r.json()["oauth_url"]
    assert "email" in url and "gmail.compose" in url and f"state={uid}&" not in url


def test_contact_emails_come_only_from_the_posting():
    job = Job(title="x", company="Acme", description="Send your CV to hr@acmeanalytics.com. Logo logo@2x.png")
    assert contact_emails(job) == ["hr@acmeanalytics.com"]
    assert contact_emails(Job(title="x", company="Acme", description="Apply on our site.")) == []


def test_application_flow_without_keys_is_honest(monkeypatch):
    for k in ("SERPAPI_KEY", "SERP_API_KEY", "FIRECRAWL_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    db = SessionLocal()
    u = User(email=f"e-{uuid.uuid4().hex[:6]}@test.local", password_hash="x"); db.add(u); db.commit(); db.refresh(u)
    db.add(CareerProfile(user_id=u.id, **PROFILE))
    job = Job(title="Data Engineer", company=f"Acme {uuid.uuid4().hex[:5]}", description=JOB["description"],
              requirements=["Python"], source_url="https://www.linkedin.com/jobs/view/1")
    db.add(job); db.commit(); db.refresh(job)
    uid, job_id = u.id, job.id
    db.close()
    h = {"Authorization": f"Bearer {create_token(uid)}"}
    from backend.services.nvidia_llm import LLMUnavailableError
    with mock.patch("backend.services.nvidia_llm.call_nvidia_json", side_effect=LLMUnavailableError("down")):
        r = client.post("/applications/prepare", json={"job_id": job_id}, headers=h)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["company"]["official_website"] == ""          # never guessed
    assert data["company"]["research"]["status"] == "not_found"
    assert data["company"]["research"]["industry"] == ""
    assert data["job"]["contact_emails"] == []
    assert "Jordan Avery" in data["email_version"]["body"]
    g = client.get(f"/companies/{data['company']['id']}/research", headers=h).json()
    assert g["status"] == "not_found" and g["claims"] == []
    bad = client.post(f"/applications/{data['id']}/gmail-draft", headers=h,
                      json={"recipient": "not-an-email", "subject": "s", "body": "b", "user_confirmed": True})
    assert bad.status_code == 400


# ---------------- recipient finder ----------------
def test_extract_and_rank_real_emails():
    text = ("Write to info@acmeanalytics.com or careers@acmeanalytics.com. noreply@acmeanalytics.com "
            "privacy@acmeanalytics.com logo@2x.png [mail](mailto:hr@acmeanalytics.com)")
    emails = cp.extract_emails(text)
    assert "noreply@acmeanalytics.com" not in emails and "privacy@acmeanalytics.com" not in emails
    assert "logo@2x.png" not in emails
    ranked = cp.rank_contacts([{"email": e, "kind": cp._email_kind(e), "source_url": "s", "on_site": True} for e in emails])
    assert ranked[0]["kind"] == "hiring" and ranked[-1]["email"] == "info@acmeanalytics.com"


def test_find_contacts_site_then_google_domain_only(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "k")
    monkeypatch.setenv("SERPAPI_KEY", "s")
    pages = {"https://acmeanalytics.com/contact": "Contact: info@acmeanalytics.com"}

    def fake_post(url, **kw):
        if url.endswith("/search"):
            return _resp(200, {"data": [{"url": "https://dir.pk/acme", "markdown": "Acme: random@gmail.com"}]})
        return _resp(200, {"data": {"markdown": pages.get(kw["json"]["url"], "")}})
    google = {"organic_results": [{"snippet": "Send CVs to jobs@acmeanalytics.com", "link": "https://x.pk/post"},
                                  {"snippet": "or someone.random@gmail.com", "link": "https://y"}]}
    with mock.patch.object(cp.requests, "post", side_effect=fake_post), \
         mock.patch.object(cp.requests, "get", return_value=_resp(200, google)):
        out = cp.find_contact_emails("Acme Analytics", "https://acmeanalytics.com")
    emails = [c["email"] for c in out["contacts"]]
    assert emails == ["jobs@acmeanalytics.com", "info@acmeanalytics.com"]   # gmail from Google is not trusted


def test_find_recipient_endpoint_uses_posting_first():
    db = SessionLocal()
    u = User(email=f"r-{uuid.uuid4().hex[:6]}@test.local", password_hash="x"); db.add(u); db.commit(); db.refresh(u)
    job = Job(title="Dev", company=f"Rec {uuid.uuid4().hex[:5]}", description="Email your CV to talent@rec.pk")
    db.add(job); db.commit(); db.refresh(job)
    from backend.models.applications import Application
    a = Application(user_id=u.id, job_id=job.id, status="DRAFT_READY"); db.add(a); db.commit(); db.refresh(a)
    uid, aid = u.id, a.id
    db.close()
    r = client.post(f"/applications/{aid}/find-recipient", headers={"Authorization": f"Bearer {create_token(uid)}"})
    assert r.status_code == 200 and r.json()["recipient"] == "talent@rec.pk"


# ---------------- CV attachment ----------------
def _app_for(profile=True):
    from backend.models.applications import Application
    db = SessionLocal()
    u = User(email=f"cv-{uuid.uuid4().hex[:6]}@test.local", password_hash="x"); db.add(u); db.commit(); db.refresh(u)
    if profile:
        db.add(CareerProfile(user_id=u.id, **PROFILE))
    job = Job(title="Dev", company=f"Att {uuid.uuid4().hex[:5]}", description="Python")
    db.add(job); db.commit(); db.refresh(job)
    a = Application(user_id=u.id, job_id=job.id, status="DRAFT_READY"); db.add(a); db.commit(); db.refresh(a)
    ids = (u.id, a.id)
    db.close()
    return ids


def test_draft_attaches_cv_from_profile_automatically():
    uid, aid = _app_for(profile=True)
    h = {"Authorization": f"Bearer {create_token(uid)}"}
    assert client.get(f"/applications/{aid}", headers=h).json()["cv_attachment"]["source"] == "profile"
    captured = {}

    def fake_draft(self, **kw):
        captured.update(kw)
        return {"provider": "gmail_live", "draft_id": "d1"}
    from backend.providers.email_providers import GmailEmailProvider
    with mock.patch.object(GmailEmailProvider, "create_draft", fake_draft):
        r = client.post(f"/applications/{aid}/gmail-draft", headers=h, json={
            "recipient": "hr@company.com", "subject": "s", "body": "b", "user_confirmed": True})
    assert r.status_code == 200, r.text
    assert captured["attachment_bytes"][:4] == b"%PDF"
    assert captured["attachment_filename"] == "Jordan_Avery_CV.pdf"
    assert r.json()["has_attachment"] is True


def test_draft_without_any_cv_is_refused_not_sent_empty():
    uid, aid = _app_for(profile=False)
    r = client.post(f"/applications/{aid}/gmail-draft", headers={"Authorization": f"Bearer {create_token(uid)}"},
                    json={"recipient": "hr@company.com", "subject": "s", "body": "b", "user_confirmed": True})
    assert r.status_code == 400 and "No CV found" in r.json()["detail"]


def test_exporter_includes_projects():
    from backend.services.resume_exporter import export_resume_docx
    import io, docx
    d = docx.Document(io.BytesIO(export_resume_docx(PROFILE)))
    assert any("Sales Pipeline" in p.text for p in d.paragraphs)


def test_hunter_and_company_panel_website(monkeypatch):
    monkeypatch.setenv("SERPAPI_KEY", "s")
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.setenv("HUNTER_API_KEY", "h")
    p = cp.FirecrawlCompanyResearchProvider(api_key="")
    panel = {"knowledge_graph": {"website": "https://www.cedargs.com/"}, "organic_results": []}
    with mock.patch.object(cp.requests, "get", return_value=_resp(200, panel)):
        site, how = p.find_official_website("Cedar Global Solutions")
    assert site == "https://cedargs.com"
    hunter = {"data": {"emails": [
        {"value": "careers@cedargs.com", "department": "hr", "sources": [{"uri": "https://cedargs.com/jobs"}]},
        {"value": "bad@cedargs.com", "verification": {"status": "invalid"}}]}}

    def fake_get(url, **kw):
        return _resp(200, hunter if "hunter.io" in url else {"organic_results": []})
    with mock.patch.object(cp.requests, "get", side_effect=fake_get):
        out = cp.find_contact_emails("Cedar Global Solutions", "https://cedargs.com")
    assert [c["email"] for c in out["contacts"]] == ["careers@cedargs.com"]
    assert out["contacts"][0]["source_url"] == "https://cedargs.com/jobs" and "Hunter.io" in out["checked"]


def test_company_panel_website_with_different_domain(monkeypatch):
    monkeypatch.setenv("SERPAPI_KEY", "s")
    p = cp.FirecrawlCompanyResearchProvider(api_key="")
    panel = {"knowledge_graph": {"website": "https://www.xyzcorp.io/"}, "organic_results": []}
    with mock.patch.object(cp.requests, "get", return_value=_resp(200, panel)):
        site, how = p.find_official_website("Northwind Traders")
    assert site == "https://xyzcorp.io" and "panel" in how


def test_tomba_domain_search(monkeypatch):
    for k in ("SERPAPI_KEY", "SERP_API_KEY", "FIRECRAWL_API_KEY", "HUNTER_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("TOMBA_API_KEY", "k"); monkeypatch.setenv("TOMBA_SECRET", "s")
    data = {"data": {"emails": [{"email": "hr@cedargs.com", "department": "hr", "sources": [{"uri": "https://cedargs.com/c"}]}]}}
    with mock.patch.object(cp.requests, "get", return_value=_resp(200, data)):
        out = cp.find_contact_emails("Cedar Global Solutions", "https://cedargs.com")
    assert out["contacts"][0]["email"] == "hr@cedargs.com" and "Tomba.io" in out["checked"]


def test_job_page_and_linkedin_post_emails(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "k"); monkeypatch.setenv("SERPAPI_KEY", "s")

    def fake_post(url, **kw):
        return _resp(200, {"data": {"markdown": "Apply: send your CV to talent.cedar@gmail.com", "links": []}})
    google = {"organic_results": [
        {"title": "Cedar Global Solutions is hiring", "snippet": "Send CV to hr@cedargs.com", "link": "https://linkedin.com/posts/1"},
        {"title": "Other company hiring", "snippet": "Send CV to someone@gmail.com", "link": "https://linkedin.com/posts/2"}]}
    with mock.patch.object(cp.requests, "post", side_effect=fake_post), \
         mock.patch.object(cp.requests, "get", return_value=_resp(200, google)):
        out = cp.find_job_contact_emails("AI Engineer", "Cedar Global Solutions", ["https://www.linkedin.com/jobs/view/1"])
    emails = [c["email"] for c in out["contacts"]]
    assert "talent.cedar@gmail.com" in emails and "hr@cedargs.com" in emails
    assert "someone@gmail.com" not in emails                       # post about another company is ignored

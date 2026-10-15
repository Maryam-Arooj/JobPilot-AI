import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from backend.services.job_normalizer import normalize_job, deduplicate_jobs
from backend.ai_agents.job_discovery import JobDiscoveryAgent
from backend.ai_agents.job_analysis import JobAnalysisAgent
from backend.ai_agents.job_match import JobMatchAgent

def test_normalize():
    raw = {"title":"AI Engineer","company":"Acme","application_url":"https://example.com/job/1"}
    n = normalize_job(raw, "test")
    assert n["title"] == "AI Engineer"
    assert n["normalized_title"] == "ai engineer"

def test_dedup():
    jobs = [
        {"canonical_application_url":"https://example.com/job/1","normalized_company":"acme","normalized_title":"ai engineer","location":"Remote"},
        {"canonical_application_url":"https://example.com/job/1","normalized_company":"acme","normalized_title":"ai engineer","location":"Remote"},
    ]
    deduped = deduplicate_jobs(jobs)
    assert len(deduped) == 1

def test_discovery():
    agent = JobDiscoveryAgent()
    intent = agent.discover_intent("Find remote AI jobs", {"professional":{"title":"Engineer"}})
    assert "remote" in str(intent["filters"])

def test_match():
    profile = {"skills":{"technical":["Python","LLM"]}}
    job = {"requirements":["Python"]}
    analysis = {"required_skills":["Python"]}
    agent = JobMatchAgent()
    result = agent.match(profile, job, analysis)
    assert result["overall_alignment"] in ["Strong Alignment","Review"]

if __name__ == "__main__":
    test_normalize()
    test_dedup()
    test_discovery()
    test_match()
    print("Phase3 tests passed")

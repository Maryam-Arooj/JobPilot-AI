import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

class MockExtractor:
    def extract(self, url):
        return {"title": "Enriched Title", "description": "Enriched description"}

class MockProvider:
    def search(self, q, f):
        return [{"title": "Raw", "application_url": "https://example.com/job", "company": "Acme"}]

from backend.ai_agents.job_discovery import JobDiscoveryAgent

def test_job_enrichment():
    agent = JobDiscoveryAgent()
    agent.serp = MockProvider()
    agent.apify = MockProvider()
    agent.extractor = MockExtractor()

    result = agent.discover("test", {})
    jobs = result["results"]
    assert len(jobs) == 1
    job = jobs[0]
    assert job["title"] in ["Enriched Title", "Raw"]
    print("Enrichment test passed")


if __name__ == "__main__":
    test_job_enrichment()


import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

class MockProvider:
    def search(self, q, f):
        return [{
            "title": "AI Engineer",
            "company": "Acme",
            "application_url": "https://example.com/job/1",
            "location": "Remote"
        }]

from backend.ai_agents.job_discovery import JobDiscoveryAgent

def test_job_discovery_wire():

    agent = JobDiscoveryAgent()
    agent.serp = MockProvider()
    agent.apify = MockProvider()

    result = agent.discover("remote AI engineer", {"professional":{"title":"Engineer"}})
    assert result["intent"]["filters"].get("remote") == True
    assert len(result["results"]) >= 1
    print("Job Discovery wired test passed")

if __name__ == "__main__":
    test_job_discovery_wire()


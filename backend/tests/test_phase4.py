import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from backend.ai_agents.application_support import ApplicationSupportAgent

def test_draft():
    agent = ApplicationSupportAgent()
    email = agent.draft_email({"title":"Engineer","company":"Acme"},{"professional":{"name":"John"}})
    assert "Engineer" in email

def test_cover():
    agent = ApplicationSupportAgent()
    letter = agent.generate_cover_letter({"title":"Engineer"}, {})
    assert "Cover letter" in letter

if __name__ == "__main__":
    test_draft()
    test_cover()
    print("Phase4 tests passed")

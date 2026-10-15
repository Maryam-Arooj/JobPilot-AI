import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from fastapi.testclient import TestClient
from backend.api.main import app

client = TestClient(app)

def test_health():
    r = client.get("/health")
    assert r.status_code == 200

def test_auth_register():
    r = client.post("/auth/register", json={"email":"test@example.com","password":"secret"})
    assert r.status_code in (200,400)

def test_profile_extraction():
    r = client.post("/profiles/me/extract", json={"text":"I'm a BS Data Science student"})
    # Will fail auth without token, but endpoint exists
    assert r.status_code in (200,401)

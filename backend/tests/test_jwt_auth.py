import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from fastapi.testclient import TestClient
from backend.api.main import app
from backend.services.auth_service import create_token

client = TestClient(app)

def test_missing_token():
    r = client.get("/profiles/me")
    assert r.status_code == 401

def test_invalid_token():
    r = client.get("/profiles/me", headers={"Authorization": "Bearer invalid"})
    assert r.status_code == 401

def test_valid_token():
    token = create_token(1)
    r = client.get("/profiles/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code in (200,404)

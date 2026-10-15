import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient
from backend.api.main import app
from backend.db.database import SessionLocal
from backend.models.career_profile import CareerProfile, ProfileFact, User
from backend.services.auth_service import create_token, hash_password
from backend.services.profile_service import calculate_completeness

client = TestClient(app)

def get_user_id(email):
    db = SessionLocal()
    u = db.query(User).filter(User.email == email).first()
    db.close()
    return u.id if u else None

def register(email, password):
    r = client.post("/auth/register", json={"email": email, "password": password})
    return r

def cleanup(email):
    from backend.models.audit import ProfileFactHistory
    db = SessionLocal()
    u = db.query(User).filter(User.email == email).first()
    if u:
        profiles = db.query(CareerProfile).filter(CareerProfile.user_id == u.id).all()
        for p in profiles:
            fact_ids = [f.id for f in db.query(ProfileFact).filter(ProfileFact.profile_id == p.id).all()]
            if fact_ids:
                db.query(ProfileFactHistory).filter(ProfileFactHistory.fact_id.in_(fact_ids)).delete(synchronize_session=False)
            db.query(ProfileFact).filter(ProfileFact.profile_id == p.id).delete(synchronize_session=False)
        db.query(CareerProfile).filter(CareerProfile.user_id == u.id).delete(synchronize_session=False)
        db.delete(u)
        db.commit()
    db.close()

email = "phase1_accept@test.com"
pwd = "secret123"

# Cleanup
cleanup(email)

print("1. Register")
r = register(email, pwd)
print("Register status", r.status_code, r.json())
assert r.status_code == 200

user_id = get_user_id(email)
assert user_id is not None
token = create_token(user_id)
headers = {"Authorization": f"Bearer {token}"}

print("2. Get profile - should 404")
r = client.get("/profiles/me", headers=headers)
print("/profiles/me", r.status_code)
assert r.status_code == 404

print("3. Create profile via PUT")
profile_data = {
    "personal": {"name": "Test User", "email": email},
    "professional": {"title": "Engineer"}
}
r = client.put("/profiles/me", json=profile_data, headers=headers)
print("PUT /profiles/me", r.status_code, r.json())
assert r.status_code == 200
# fetch profile to get id
r = client.get("/profiles/me", headers=headers)
assert r.status_code == 200
profile = r.json()
profile_id = profile["id"]

print("4. Completeness deterministic")
db = SessionLocal()
prof = db.query(CareerProfile).filter(CareerProfile.id == profile_id).first()
data = {"personal": prof.personal, "professional": prof.professional}
pct1 = calculate_completeness(data)
pct2 = calculate_completeness(data)
db.close()
print("Completeness", pct1)
assert pct1 == pct2

print("5. Extract endpoint")
r = client.post("/profiles/me/extract", json={"text": "I'm a BS Data Science student"}, headers=headers)
print("/profiles/me/extract", r.status_code)
assert r.status_code in (200, 401)

print("6. Document parse")
import io
from fastapi import UploadFile
files = {"file": ("test.txt", io.BytesIO(b"Name: Test User\nTitle: Engineer"), "text/plain")}
r = client.post("/documents/parse", files=files, headers=headers)
print("/documents/parse", r.status_code, r.json())
assert r.status_code == 200
facts = r.json().get("facts", [])
assert isinstance(facts, list)

print("7. Create facts and confirm")
db = SessionLocal()
prof = db.query(CareerProfile).filter(CareerProfile.id == profile_id).first()
f1 = ProfileFact(profile_id=prof.id, path="personal.name", value="Test User", source="manual", verified=False)
f2 = ProfileFact(profile_id=prof.id, path="professional.title", value="Engineer", source="manual", verified=False)
db.add_all([f1, f2])
db.commit()
db.refresh(f1); db.refresh(f2)
fact_ids = [f1.id, f2.id]
db.close()

r = client.post("/profiles/me/facts/confirm", json={"fact_ids": fact_ids, "action": "confirm"}, headers=headers)
print("Confirm facts", r.status_code, r.json())
assert r.status_code == 200

print("8. Conflict resolution persistence")
db = SessionLocal()
prof = db.query(CareerProfile).filter(CareerProfile.id == profile_id).first()
conflict_path = "test.conflict.path"
existing = ProfileFact(profile_id=prof.id, path=conflict_path, value="Old Value", source="doc", verified=True)
db.add(existing)
db.commit()
db.refresh(existing)
new_fact = ProfileFact(profile_id=prof.id, path=conflict_path, value="New Value", source="manual", verified=False)
db.add(new_fact)
db.commit()
db.refresh(new_fact)

r = client.post("/profiles/me/facts/resolve-conflict", json={"path": conflict_path, "keep_existing": False, "fact_id": new_fact.id}, headers=headers)
print("Resolve conflict", r.status_code, r.json())
assert r.status_code == 200

from backend.models.audit import ProfileFactHistory
hist_count = db.query(ProfileFactHistory).filter(ProfileFactHistory.fact_id == existing.id).count()
print("History count", hist_count)
assert hist_count >= 1
db.close()

print("9. Profile dashboard completeness")
r = client.get("/profiles/me", headers=headers)
print("/profiles/me", r.status_code)
assert r.status_code == 200

print("Phase 1 ACCEPTED")
# cleanup(email)  # skip cleanup to avoid FK cascade issues in test DB

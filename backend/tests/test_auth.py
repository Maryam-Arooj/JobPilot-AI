from services.auth_service import hash_password, verify_password, create_token

def test_password_hash():
    pw = "secret"
    h = hash_password(pw)
    assert verify_password(pw, h)
    assert not verify_password("wrong", h)

def test_token():
    t = create_token(1)
    assert isinstance(t, str) and len(t) > 0

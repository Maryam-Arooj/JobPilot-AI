import os
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from dotenv import load_dotenv

load_dotenv()

def get_secret_key() -> str:
    return os.getenv("SECRET_KEY", "change-me")

ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")

def hash_password(pw: str) -> str:
    # bcrypt max 72 bytes
    pw_bytes = pw.encode('utf-8')[:72]
    pw_truncated = pw_bytes.decode('utf-8', errors='ignore')
    return pwd_context.hash(pw_truncated)

def verify_password(pw: str, hashed: str) -> bool:
    pw_bytes = pw.encode('utf-8')[:72]
    pw_truncated = pw_bytes.decode('utf-8', errors='ignore')
    return pwd_context.verify(pw_truncated, hashed)

def create_token(user_id: int) -> str:
    expire = datetime.utcnow() + timedelta(days=7)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, get_secret_key(), algorithm=ALGORITHM)

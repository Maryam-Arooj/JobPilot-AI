import os
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db.database import get_db
from ..models.applications import GmailConnection
from ..services.auth_middleware import get_current_user_id

logger = logging.getLogger(__name__)

STATE_TTL = 15 * 60  # seconds


def _secret() -> bytes:
    return os.getenv("SECRET_KEY", "change-me").encode()


def make_state(user_id: int, now: float = None) -> str:
    """Signed OAuth state: user id + expiry + HMAC, so nobody can connect their Gmail to another account."""
    import base64, hashlib, hmac, secrets, time
    exp = int((now or time.time()) + STATE_TTL)
    payload = f"{user_id}.{exp}.{secrets.token_hex(8)}"
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return base64.urlsafe_b64encode(f"{payload}.{sig}".encode()).decode().rstrip("=")


def read_state(state: str, now: float = None) -> int:
    import base64, hashlib, hmac, time
    try:
        raw = base64.urlsafe_b64decode(state + "=" * (-len(state) % 4)).decode()
        uid, exp, nonce, sig = raw.split(".")
        good = hmac.new(_secret(), f"{uid}.{exp}.{nonce}".encode(), hashlib.sha256).hexdigest()[:32]
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid OAuth state. Please click Connect Gmail again.")
    if not hmac.compare_digest(sig, good):
        raise HTTPException(status_code=400, detail="Invalid OAuth state. Please click Connect Gmail again.")
    if int(exp) < (now or time.time()):
        raise HTTPException(status_code=400, detail="The Gmail connect link expired. Please click Connect Gmail again.")
    return int(uid)

router = APIRouter(prefix="/gmail", tags=["gmail"])

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI",
    "http://localhost:3000/api/auth/callback/google"
)

@router.get("/status")
def get_gmail_status(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    """Returns real Gmail connection status from database."""
    # First check if Gmail OAuth credentials are even configured
    if not GOOGLE_CLIENT_ID:
        return {
            "connected": False,
            "email": None,
            "configuration_error": "GOOGLE_CLIENT_ID is not set in backend/.env. Gmail OAuth cannot function without this credential.",
            "setup_required": True,
        }

    conn = db.query(GmailConnection).filter(GmailConnection.user_id == user_id).first()
    if not conn or not conn.is_connected:
        return {
            "connected": False,
            "email": None,
            "setup_required": False,
        }
    return {
        "connected": True,
        "email": conn.email,
        "setup_required": False,
    }

@router.get("/oauth/start")
def oauth_start(user_id: int = Depends(get_current_user_id)):
    """Generates real Google OAuth URL using configured credentials."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=503,
            detail=(
                "Gmail OAuth is not configured. "
                "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in backend/.env "
                "to enable Gmail integration. "
                "See: https://console.cloud.google.com/apis/credentials"
            ),
        )

    import urllib.parse
    scope = "openid email https://www.googleapis.com/auth/gmail.compose"
    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        + urllib.parse.urlencode({
            "response_type": "code",
            "client_id": GOOGLE_CLIENT_ID,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "scope": scope,
            "access_type": "offline",
            "prompt": "consent",
            "state": make_state(user_id),
        })
    )
    return {"oauth_url": auth_url}

@router.get("/oauth/callback")
def oauth_callback(code: str, state: str = None, db: Session = Depends(get_db)):
    """Exchanges OAuth code for real tokens and stores them."""
    if not code:
        raise HTTPException(status_code=400, detail="OAuth authorization code missing")
    if not state:
        raise HTTPException(status_code=400, detail="OAuth state missing (required for user identification)")
    
    user_id = read_state(state)

    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
    if not GOOGLE_CLIENT_ID or not client_secret:
        raise HTTPException(
            status_code=503,
            detail="GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in backend/.env to complete OAuth."
        )

    import requests as req
    token_response = req.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": client_secret,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=20,
    )

    if token_response.status_code != 200:
        logger.error(
            "Google token exchange failed (HTTP %s): %s",
            token_response.status_code, token_response.text[:300]
        )
        raise HTTPException(status_code=502, detail="Google token exchange failed")

    token_data = token_response.json()
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token", "")

    # Get user's Gmail address
    email = ""
    for url, key in (("https://openidconnect.googleapis.com/v1/userinfo", "email"),
                     ("https://gmail.googleapis.com/gmail/v1/users/me/profile", "emailAddress")):
        try:
            r = req.get(url, headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
            if r.status_code == 200 and r.json().get(key):
                email = r.json()[key]
                break
        except Exception:
            logger.warning("Could not read the Gmail address from %s", url)
    if not email:
        logger.warning("Gmail connected but the address could not be read; reconnect to show it.")
    from datetime import datetime, timedelta, timezone
    expiry = (datetime.now(timezone.utc) + timedelta(seconds=int(token_data["expires_in"]))
              if token_data.get("expires_in") else None)

    conn = db.query(GmailConnection).filter(GmailConnection.user_id == user_id).first()
    if not conn:
        conn = GmailConnection(
            user_id=user_id,
            email=email,
            is_connected=True,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expiry=expiry,
        )
        db.add(conn)
    else:
        conn.is_connected = True
        conn.email = email or conn.email
        conn.access_token = access_token
        conn.token_expiry = expiry
        if refresh_token:
            conn.refresh_token = refresh_token

    db.commit()
    return {"status": "success", "connected": True, "email": email}

@router.post("/disconnect")
def disconnect_gmail(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    conn = db.query(GmailConnection).filter(GmailConnection.user_id == user_id).first()
    if conn:
        conn.is_connected = False
        conn.access_token = None
        conn.refresh_token = None
        db.commit()
    return {"status": "disconnected"}

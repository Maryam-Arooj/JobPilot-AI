import os
import base64
import logging
import requests

from ..services.agent_runs import tool_call
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

logger = logging.getLogger(__name__)

class GmailNotConnectedError(Exception):
    """User has no active Gmail OAuth connection."""

class GmailDraftError(Exception):
    """Gmail API call failed; details are logged server-side only."""

class EmailProvider(ABC):
    @abstractmethod
    def create_draft(
        self,
        user_id: int,
        recipient: str,
        subject: str,
        body: str,
        attachment_bytes: Optional[bytes] = None,
        attachment_filename: Optional[str] = None,
        sender_email: Optional[str] = None,
        db_session: Optional[Any] = None
    ) -> Dict[str, Any]:
        pass

class GmailEmailProvider(EmailProvider):
    def __init__(self):
        self.client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        self.client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
        self.redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:3000/api/auth/callback/google")

    def _refresh_access_token(self, refresh_token: str) -> Optional[str]:
        if not self.client_id or not self.client_secret or not refresh_token:
            return None
        try:
            resp = requests.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token"
                },
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("access_token")
        except Exception:
            logger.exception("Gmail token refresh error")
        return None

    def create_draft(
        self,
        user_id: int,
        recipient: str,
        subject: str,
        body: str,
        attachment_bytes: Optional[bytes] = None,
        attachment_filename: Optional[str] = None,
        sender_email: Optional[str] = None,
        db_session: Optional[Any] = None
    ) -> Dict[str, Any]:
        if not recipient or "@" not in recipient:
            raise ValueError("Valid email recipient is required before creating draft")

        from_address = sender_email or "applicant@yourcareerbuddy.com"

        # Build RFC 2822 MIME message
        message = MIMEMultipart()
        message['From'] = from_address
        message['To'] = recipient
        message['Subject'] = subject
        message.attach(MIMEText(body, 'plain', 'utf-8'))

        if attachment_bytes:
            filename = attachment_filename or "Resume.pdf"
            part = MIMEApplication(attachment_bytes, Name=filename)
            part['Content-Disposition'] = f'attachment; filename="{filename}"'
            message.attach(part)

        raw_bytes = message.as_bytes()
        raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode('utf-8')

        # Check if user has an active Gmail OAuth connection in database
        gmail_conn = None
        if db_session:
            from ..models.applications import GmailConnection
            gmail_conn = db_session.query(GmailConnection).filter(
                GmailConnection.user_id == user_id,
                GmailConnection.is_connected == True
            ).first()

        if not gmail_conn or not gmail_conn.access_token:
            raise GmailNotConnectedError("Gmail is not connected for this user")

        headers = {
            "Authorization": f"Bearer {gmail_conn.access_token}",
            "Content-Type": "application/json"
        }
        draft_payload = {"message": {"raw": raw_b64}}
        try:
            with tool_call("gmail:drafts.create", "create draft") as tc:
                draft_resp = requests.post(
                    "https://gmail.googleapis.com/gmail/v1/users/me/drafts",
                    headers=headers,
                    json=draft_payload,
                    timeout=15
                )
                tc["summary"] = f"HTTP {draft_resp.status_code}"
                if draft_resp.status_code not in (200, 201):
                    tc["status"] = "failed"

            if draft_resp.status_code == 401 and gmail_conn.refresh_token:
                # Token expired; try refreshing
                with tool_call("google:oauth.refresh", "refresh expired Gmail token") as tc:
                    new_token = self._refresh_access_token(gmail_conn.refresh_token)
                    tc["summary"] = "token refreshed" if new_token else "refresh failed"
                    if not new_token:
                        tc["status"] = "failed"
                if new_token:
                    gmail_conn.access_token = new_token
                    db_session.commit()
                    headers["Authorization"] = f"Bearer {new_token}"
                    with tool_call("gmail:drafts.create", "retry with refreshed token") as tc:
                        draft_resp = requests.post(
                            "https://gmail.googleapis.com/gmail/v1/users/me/drafts",
                            headers=headers,
                            json=draft_payload,
                            timeout=15
                        )
                        tc["summary"] = f"HTTP {draft_resp.status_code}"
                        if draft_resp.status_code not in (200, 201):
                            tc["status"] = "failed"
        except requests.RequestException as e:
            logger.error("Gmail draft request failed for user %s: %s", user_id, e)
            raise GmailDraftError("Gmail API request failed") from e

        draft_id = None
        if draft_resp.status_code in (200, 201):
            draft_id = (draft_resp.json() or {}).get("id")
        if not draft_id:
            logger.error(
                "Gmail draft API returned HTTP %s for user %s: %s",
                draft_resp.status_code, user_id, draft_resp.text[:300]
            )
            raise GmailDraftError(f"Gmail API returned HTTP {draft_resp.status_code}")

        return {
            "status": "success",
            "provider": "gmail_live",
            "draft_id": draft_id,
            "sender": from_address,
            "recipient": recipient,
            "subject": subject,
            "has_attachment": bool(attachment_bytes),
            "attachment_name": attachment_filename,
            "message": f"Gmail draft created live in your account ({from_address})!"
        }


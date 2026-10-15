import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class SMTPNotConfiguredError(Exception):
    """SMTP_USER / SMTP_PASSWORD are not set, so nothing can be sent."""

class SMTPDeliveryError(Exception):
    """SMTP send failed; details are logged server-side only."""

class EmailSenderService:
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", os.getenv("EMAIL_USER", ""))
        self.smtp_pass = os.getenv("SMTP_PASSWORD", os.getenv("EMAIL_PASSWORD", ""))
        self.from_email = os.getenv("FROM_EMAIL", self.smtp_user or "career-agent@yourcareerbuddy.com")

    def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        attachment_bytes: Optional[bytes] = None,
        attachment_filename: Optional[str] = None,
        is_html: bool = False
    ) -> Dict[str, Any]:
        """
        Directly send email using Python smtplib with optional attachments.
        Raises SMTPNotConfiguredError if SMTP credentials are not configured,
        and SMTPDeliveryError if the SMTP server rejects or fails the send.
        """
        if not to_email or "@" not in to_email:
            raise ValueError(f"Invalid recipient email address: '{to_email}'")

        # Create message container
        msg = MIMEMultipart()
        msg["From"] = self.from_email
        msg["To"] = to_email
        msg["Subject"] = subject

        # Attach text or html body
        content_type = "html" if is_html else "plain"
        msg.attach(MIMEText(body, content_type, "utf-8"))

        # Attach document if provided
        if attachment_bytes and attachment_filename:
            part = MIMEApplication(attachment_bytes, Name=attachment_filename)
            part["Content-Disposition"] = f'attachment; filename="{attachment_filename}"'
            msg.attach(part)

        if not (self.smtp_user and self.smtp_pass):
            raise SMTPNotConfiguredError("SMTP is not configured")

        try:
            server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=20)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(self.smtp_user, self.smtp_pass)
            server.sendmail(self.from_email, [to_email], msg.as_string())
            server.quit()
        except Exception as e:
            logger.error("SMTP delivery error: %s", e)
            raise SMTPDeliveryError("SMTP delivery failed") from e

        logger.info(f"Live email dispatched directly via SMTP to {to_email}")
        return {
            "status": "sent",
            "delivery_mode": "live_smtp",
            "recipient": to_email,
            "subject": subject,
            "has_attachment": bool(attachment_bytes),
            "attachment_name": attachment_filename,
            "message": f"Email successfully delivered to {to_email} via native Python SMTP service."
        }

import os
import smtplib
import socket
import sqlite3
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import make_msgid


class EmailSender:
    def __init__(self, dry_run=None):
        self.dry_run = (
            os.environ.get("EMAIL_DRY_RUN", "true").lower() == "true"
            if dry_run is None
            else dry_run
        )

        self.sender_email = os.environ.get("SENDER_EMAIL")
        self.sender_password = os.environ.get("SENDER_APP_PASSWORD")
        self.smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.environ.get("SMTP_PORT", "587"))

    def send(self, recipient_email, subject, body):
        if self.dry_run:
            return {
                "status": "dry_run",
                "recipient": recipient_email,
                "subject": subject,
            }

        # Phase 6.3: fail safely rather than raising — a missing credential
        # or a network blip must not crash the whole agent loop.
        if not self.sender_email or not self.sender_password:
            return {
                "status": "error",
                "recipient": recipient_email,
                "subject": subject,
                "error": "SENDER_EMAIL / SENDER_APP_PASSWORD not set.",
            }

        message_id = make_msgid()

        msg = MIMEMultipart()
        msg["From"] = self.sender_email
        msg["To"] = recipient_email
        msg["Subject"] = subject
        msg["Message-ID"] = message_id
        msg.attach(MIMEText(body, "plain"))

        try:
            server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=20)
        except (OSError, socket.error) as exc:
            return {
                "status": "error", "recipient": recipient_email, "subject": subject,
                "error": f"could not connect to SMTP server: {exc}",
            }

        try:
            server.starttls()
            server.login(self.sender_email, self.sender_password)

            server.sendmail(
                self.sender_email,
                recipient_email,
                msg.as_string(),
            )

            return {
                "status": "sent",
                "recipient": recipient_email,
                "subject": subject,
                "message_id": message_id,
            }

        except smtplib.SMTPException as exc:
            return {
                "status": "error", "recipient": recipient_email, "subject": subject,
                "error": f"SMTP send failed: {exc}",
            }
        finally:
            try:
                server.quit()
            except Exception:
                pass
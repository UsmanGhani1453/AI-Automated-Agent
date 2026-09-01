import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


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

        if not self.sender_email or not self.sender_password:
            raise RuntimeError(
                "SENDER_EMAIL / SENDER_APP_PASSWORD not set."
            )

        msg = MIMEMultipart()
        msg["From"] = self.sender_email
        msg["To"] = recipient_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        server = smtplib.SMTP(self.smtp_server, self.smtp_port)

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
            }

        finally:
            server.quit()
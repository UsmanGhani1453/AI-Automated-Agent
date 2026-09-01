from app.tools.base import Tool
from app.email.sender import EmailSender


class GmailTool(Tool):
    name = "gmail"

    def __init__(self, dry_run=False):
        self.sender = EmailSender(dry_run=dry_run)

    def execute(self, recipient_email, subject, body):
        return self.sender.send(
            recipient_email=recipient_email,
            subject=subject,
            body=body,
        )
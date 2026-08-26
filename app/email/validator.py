"""Validator: last-line checks before an email is allowed to be sent."""
import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailValidator:
    def validate_lead(self, lead: dict) -> (bool, str):
        if not lead.get("email") or not EMAIL_RE.match(lead["email"]):
            return False, "invalid or missing recipient email"
        if not lead.get("officer") and not lead.get("company"):
            return False, "lead has no name/company to personalize with"
        return True, "ok"

    def validate_email_body(self, body: str, analyzer_report: dict) -> (bool, str):
        if analyzer_report.get("placeholder_found"):
            return False, "unresolved placeholder detected"
        if analyzer_report.get("word_count", 0) < 15:
            return False, "email too short to be credible"
        if analyzer_report.get("spam_risk", 0) >= 0.66:
            return False, "spam risk too high"
        return True, "ok"

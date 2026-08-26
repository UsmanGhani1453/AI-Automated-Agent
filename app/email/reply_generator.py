"""Safe, model-free inbox classification and draft generation."""
from __future__ import annotations

import re
from email.utils import parseaddr


class ReplyGenerator:
    AUTOMATED_SENDERS = {
        "no-reply", "noreply", "no_reply", "donotreply", "do-not-reply",
        "mailer-daemon", "postmaster"
    }
    AUTOMATED_DOMAINS = {"accounts.google.com", "google.com"}
    SECURITY_TERMS = {
        "security alert", "app password", "password changed", "recovery email",
        "recovery phone", "new sign-in", "suspicious activity", "verification code",
        "two-step verification", "2-step verification"
    }
    PROMO_TERMS = {
        "unsubscribe", "newsletter", "prize pool", "limited time", "special offer",
        "sale", "discount", "deal", "promotion", "marketing"
    }

    def __init__(self, sender_info: dict | None = None) -> None:
        self.sender_info = sender_info or {}

    @staticmethod
    def _first_name(from_header: str) -> str:
        name, address = parseaddr(from_header or "")
        if name:
            return name.split()[0]
        if address and "@" in address:
            return address.split("@", 1)[0].replace(".", " ").split()[0].title()
        return "there"

    @staticmethod
    def _clean_subject(subject: str) -> str:
        return re.sub(r"^(?:(?:re|fw|fwd):\s*)+", "", subject or "", flags=re.I).strip()

    @staticmethod
    def _sender_localpart(address: str) -> str:
        return (address or "").split("@", 1)[0].lower().strip()

    def classify(self, message: dict) -> tuple[str, str]:
        subject = (message.get("subject") or "").lower()
        body = (message.get("body") or "").lower()
        sender = (message.get("from_email") or parseaddr(message.get("from", ""))[1]).lower()
        local = self._sender_localpart(sender)
        domain = sender.rsplit("@", 1)[-1] if "@" in sender else ""

        if local in self.AUTOMATED_SENDERS:
            return "automated", "sender address indicates automated mail"
        if domain in self.AUTOMATED_DOMAINS and any(term in subject for term in self.SECURITY_TERMS):
            return "security", "account/security notification"
        if any(term in subject or term in body[:4000] for term in self.SECURITY_TERMS):
            return "security", "security/account notification"
        if any(term in subject for term in self.PROMO_TERMS) or "unsubscribe" in body:
            return "promotional", "newsletter or promotional content"
        if not (message.get("body") or "").strip():
            return "empty", "no readable message body"
        return "actionable", "likely human/actionable message"

    def draft(self, message: dict) -> dict:
        category, reason = self.classify(message)
        subject = self._clean_subject(message.get("subject", ""))
        if category != "actionable":
            return {"category": category, "reason": reason, "subject": subject, "body": "", "should_reply": False}

        first_name = self._first_name(message.get("from", ""))
        body = " ".join((message.get("body") or "").split())
        excerpt = body[:420].strip()
        if len(body) > 420:
            excerpt += "..."
        sender_name = self.sender_info.get("sender_name", "")
        sender_title = self.sender_info.get("sender_title", "")

        reply_body = (
            f"Hi {first_name},\n\n"
            f"Thanks for your message regarding {subject or 'this'}. "
            f"I’ve reviewed the details you sent."
        )
        if excerpt:
            reply_body += f"\n\nYou mentioned: {excerpt}"
        reply_body += (
            "\n\nI’ll review this and get back to you with the relevant details."
            "\n\nBest regards,"
            f"\n{sender_name}\n{sender_title}"
        )
        return {
            "category": category,
            "reason": reason,
            "subject": f"Re: {subject}" if subject else "Re:",
            "body": reply_body,
            "should_reply": True,
        }

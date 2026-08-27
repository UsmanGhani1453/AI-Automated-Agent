"""Deterministic email understanding for the adaptive email agent."""
from __future__ import annotations

import re
from email.utils import parseaddr


class EmailUnderstanding:
    AUTOMATED_LOCALPARTS = {
        "no-reply",
        "noreply",
        "no_reply",
        "donotreply",
        "do-not-reply",
        "mailer-daemon",
        "postmaster",
    }

    SECURITY_TERMS = {
        "security alert",
        "verification code",
        "password reset",
        "password changed",
        "new sign-in",
        "suspicious activity",
        "two-factor",
        "two factor",
        "two step",
        "two-step verification",
        "recovery email",
        "recovery phone",
        "app password",
    }

    URGENT_TERMS = {
        "urgent",
        "asap",
        "immediately",
        "today",
        "deadline",
        "past due",
        "overdue",
        "time sensitive",
        "time-sensitive",
    }

    MEETING_PATTERNS = (
        r"\b(schedule|book|arrange|set up)\b.{0,80}\b(call|meeting|demo)\b",
        r"\b(can|could|would)\s+(we|you)\s+have\b.{0,80}\b(call|meeting)\b",
        r"\b(quick|short|brief)\s+(call|meeting)\b",
        r"\bavailable\b.{0,80}\b(call|meeting)\b",
        r"\bfree\b.{0,50}\b(call|meeting)\b",
    )

    INFORMATION_PATTERNS = (
        r"\b(send|share|provide)\b.{0,80}\b(details|information|document|file)\b",
        r"\b(can|could|would)\s+you\b.{0,100}\b(send|share|provide)\b",
        r"\bplease\b.{0,100}\b(send|share|provide)\b",
    )

    APPROVAL_PATTERNS = (
        r"\b(approve|approval|sign[- ]?off)\b",
        r"\bcan you approve\b",
        r"\bplease approve\b",
    )

    FOLLOW_UP_PATTERNS = (
        r"\bfollow(?:ing)? up\b",
        r"\bchecking in\b",
        r"\bany update\b",
        r"\bjust wanted to check\b",
    )

    @staticmethod
    def clean_subject(subject: str) -> str:
        return re.sub(
            r"^(?:(?:re|fw|fwd):\s*)+",
            "",
            subject or "",
            flags=re.I,
        ).strip()

    @staticmethod
    def _sender(message: dict) -> str:
        return (
            message.get("from_email")
            or parseaddr(message.get("from", ""))[1]
            or ""
        ).lower().strip()

    @staticmethod
    def _matches(patterns, text: str) -> bool:
        return any(
            re.search(pattern, text, re.I | re.S)
            for pattern in patterns
        )

    @staticmethod
    def _extract_requested_action(body: str) -> str:
        text = " ".join(body.split())

        patterns = [
            r"\b(?:can|could|would)\s+you\s+(.{3,160}?)(?:[?.]|$)",
            r"\b(?:can|could|would)\s+we\s+(.{3,160}?)(?:[?.]|$)",
            r"\bplease\s+(.{3,160}?)(?:[?.]|$)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                return match.group(1).strip()

        return ""

    @staticmethod
    def _extract_time_reference(body: str) -> str:
        patterns = [
            r"\b(?:tomorrow|today|tonight)\b",
            r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b",
            r"\b\d{1,2}\s*(?:am|pm)\b",
        ]

        for pattern in patterns:
            match = re.search(pattern, body, re.I)
            if match:
                return match.group(0)

        return ""

    def analyze(self, message: dict) -> dict:
        subject = self.clean_subject(message.get("subject", ""))
        body = (message.get("body") or "").strip()

        sender = self._sender(message)
        local = sender.split("@", 1)[0] if "@" in sender else sender

        haystack = f"{subject}\n{body[:8000]}".lower()

        # Category first.
        if not body:
            category = "empty"
        elif any(term in haystack for term in self.SECURITY_TERMS):
            category = "security"
        elif local in self.AUTOMATED_LOCALPARTS:
            category = "automated"
        else:
            category = "actionable"

        # Intent priority matters.
        if category == "security":
            intent = "security_notification"

        elif category == "automated":
            intent = "automated_notification"

        elif category == "empty":
            intent = "none"

        elif self._matches(self.MEETING_PATTERNS, haystack):
            intent = "meeting_request"

        elif self._matches(self.APPROVAL_PATTERNS, haystack):
            intent = "approval_request"

        elif self._matches(self.INFORMATION_PATTERNS, haystack):
            intent = "information_request"

        elif self._matches(self.FOLLOW_UP_PATTERNS, haystack):
            intent = "follow_up"

        elif "?" in body:
            intent = "question"

        else:
            intent = "general_request"

        urgency_hits = sorted(
            {
                term
                for term in self.URGENT_TERMS
                if term in haystack
            }
        )

        # Security changes are always high priority.
        if category == "security":
            urgency = "high"
        else:
            urgency = "high" if urgency_hits else "normal"

        requested_action = self._extract_requested_action(body)
        time_reference = self._extract_time_reference(body)

        should_reply = category == "actionable"

        return {
            "category": category,
            "intent": intent,
            "urgency": urgency,
            "urgency_terms": urgency_hits,
            "requested_action": requested_action,
            "time_reference": time_reference,
            "should_reply": should_reply,
            "sender_email": sender,
            "subject": subject,
        }

    @classmethod
    def build_thread_key(cls, message: dict) -> str:
        explicit = (message.get("thread_key") or "").strip()

        if explicit:
            return explicit

        analysis = cls().analyze(message)

        # Security alerts with the same subject are separate events.
        if analysis["category"] == "security":
            message_id = (
                message.get("message_id")
                or message.get("id")
                or "unknown"
            )
            return f"security:{message_id}"

        subject = analysis["subject"].lower()
        sender = cls._sender(message)

        normalized_subject = re.sub(r"\s+", " ", subject)

        # A missing subject is still a valid conversation key.
        if not normalized_subject:
            return f"{sender}|no-subject"

        return f"{sender}|{normalized_subject}"
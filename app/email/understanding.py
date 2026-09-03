"""Deterministic email understanding for the adaptive email agent."""
from __future__ import annotations

import difflib
import re
from email.utils import parseaddr


class EmailUnderstanding:
    AUTOMATED_LOCALPARTS = frozenset({
        "no-reply", "noreply", "no_reply", "donotreply", "do-not-reply",
        "mailer-daemon", "postmaster", "system", "alerts",
    })

    SECURITY_TERMS = (
        "security alert", "verification code", "password reset",
        "password changed", "new sign-in", "suspicious activity",
        "two-factor", "two factor", "two step", "two-step verification",
        "recovery email", "recovery phone", "app password",
    )

    URGENT_TERMS = (
        "urgent", "asap", "immediately", "today", "deadline",
        "past due", "overdue", "time sensitive", "time-sensitive",
    )

    # Pre-compile boundary-safe regexes for exact word matching
    _SECURITY_RE = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in SECURITY_TERMS) + r")\b", re.I)
    _URGENCY_RE = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in URGENT_TERMS) + r")\b", re.I)

    MEETING_PATTERNS = (
        r"\b(?:schedule|book|arrange|set up)\b.{0,80}\b(?:call|meeting|demo)\b",
        r"\b(?:can|could|would)\s+(?:we|you)\s+have\b.{0,80}\b(?:call|meeting)\b",
        r"\b(?:quick|short|brief)\s+(?:call|meeting)\b",
        r"\bavailable\b.{0,80}\b(?:call|meeting)\b",
        r"\bfree\b.{0,50}\b(?:call|meeting)\b",
        # Casual, standalone availability questions ("are u available",
        # "you available today?", "are you free") with no "call/meeting"
        # nearby — these still mean the sender wants to know availability.
        r"\bare\s+(?:you|u)\s+(?:available|free)\b",
        r"\b(?:you|u)\s+available\b",
        r"\b(?:you|u)\s+free\b",
        # "hold/have a meeting" phrasing, including broken/non-native
        # English like "when we held our meeting" (meant as "when can
        # we hold our meeting").
        r"\b(?:hold|held|holding|have|having)\b.{0,40}\b(?:meeting|call)\b",
        r"\bwhen\b.{0,40}\b(?:meeting|call)\b",
        # "schedule"/"set up" used on their own, with no object stated
        # ("when we schedule", "how do we set up") — in an outreach
        # inbox this almost always means scheduling a call/meeting even
        # though the message never says the word "call" or "meeting".
        r"\b(?:when|how)\b.{0,20}\b(?:we|you|i)\b.{0,20}\bschedule\b",
        r"\blet'?s\s+schedule\b",
    )

    # Price / rate questions — canonical keywords, checked both as exact
    # words and via fuzzy matching (see _fuzzy_matches_price) to tolerate
    # typos like "chages" for "charges" in casual/mobile-typed replies.
    PRICE_KEYWORDS = (
        "price", "pricing", "rate", "rates", "cost", "costs",
        "fee", "fees", "charge", "charges", "percentage", "commission",
    )

    PRICE_PATTERNS = (
        r"\b(?:price|pricing|rate|rates|cost|costs|fee|fees|charge|charges|percentage|commission)\b",
        r"\bhow much\b",
        r"\bwhat do you charge\b",
    )

    INFORMATION_PATTERNS = (
        r"\b(?:send|share|provide)\b.{0,80}\b(?:details|information|document|file)\b",
        r"\b(?:can|could|would)\s+you\b.{0,100}\b(?:send|share|provide)\b",
        r"\bplease\b.{0,100}\b(?:send|share|provide)\b",
    )

    APPROVAL_PATTERNS = (
        r"\b(?:approve|approval|sign[- ]?off)\b",
        r"\bcan you approve\b",
        r"\bplease approve\b",
    )

    FOLLOW_UP_PATTERNS = (
        r"\bfollow(?:ing)? up\b", r"\bchecking in\b",
        r"\bany update\b", r"\bjust wanted to check\b",
    )

    # Explicit rejection / opt-out — must be checked ahead of every other
    # intent (including "question"/"general_request") so a "not interested"
    # reply never gets treated as an open sales lead.
    DISENGAGEMENT_PATTERNS = (
        r"\bnot interested\b",
        r"\bno longer interested\b",
        r"\bno thanks?\b",
        r"\bnot for us\b",
        r"\bnot right now\b",
        r"\bplease stop\b",
        r"\bstop (?:emailing|contacting|messaging) (?:me|us)\b",
        r"\bremove me\b",
        r"\btake me off\b",
        r"\bdon'?t contact\b",
        r"\bunsubscribe\b",
    )

    # Question words that signal a real question even without a "?"
    # (casual texting style, e.g. "what are the charges", "when can we start")
    _QUESTION_WORD_RE = re.compile(
        r"^\s*(?:what|when|where|why|how|who|which|are|is|do|does|did|can|could|would|will)\b",
        re.I,
    )

    @staticmethod
    def clean_subject(subject: str) -> str:
        return re.sub(
            r"^(?:(?:re|fw|fwd|aw|antw):\s*)+",  # common international prefixes
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
    def _matches(patterns: tuple, text: str) -> bool:
        return any(re.search(pattern, text, re.I | re.S) for pattern in patterns)

    @classmethod
    def _fuzzy_matches_price(cls, text: str) -> bool:
        """
        Catch common typos of price-related words (e.g. "chages" for
        "charges", "pric" for "price") that exact regex matching would
        otherwise miss entirely. Only checks words of length >= 4 to
        avoid false positives on short unrelated words, and requires a
        high similarity ratio so it doesn't match unrelated words.
        """
        words = re.findall(r"[a-zA-Z']+", text)

        for word in words:
            lower_word = word.lower()

            if len(lower_word) < 4:
                continue

            close = difflib.get_close_matches(
                lower_word,
                cls.PRICE_KEYWORDS,
                n=1,
                cutoff=0.8,
            )

            if close:
                return True

        return False

    @staticmethod
    def _extract_requested_action(body: str) -> str:
        text = " ".join(body.split())
        patterns = (
            r"\b(?:can|could|would)\s+you\s+(.{3,160}?)(?:[?.]|$)",
            r"\b(?:can|could|would)\s+we\s+(.{3,160}?)(?:[?.]|$)",
            r"\bplease\s+(.{3,160}?)(?:[?.]|$)",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                return match.group(1).strip()
        return ""

    @staticmethod
    def _extract_time_reference(body: str) -> str:
        # Expanded to catch days of the week, "next week", and 24h time
        patterns = (
            r"\b(?:tomorrow|today|tonight|next week)\b",
            r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
            r"\b(?:0?[1-9]|1[0-2])(?::[0-5][0-9])?\s*(?:am|pm)\b",
            r"\b(?:[01]?[0-9]|2[0-3]):[0-5][0-9]\b",  # 24h format (e.g., 14:30)
        )
        for pattern in patterns:
            match = re.search(pattern, body, re.I)
            if match:
                return match.group(0).lower()
        return ""

    def analyze(self, message: dict) -> dict:
        subject = self.clean_subject(message.get("subject", ""))
        body = (message.get("body") or "").strip()

        sender = self._sender(message)
        local = sender.split("@", 1)[0] if "@" in sender else sender

        haystack = f"{subject}\n{body[:8000]}".lower()

        # Extract urgency hits safely using compiled regex boundaries
        urgency_hits = sorted(set(self._URGENCY_RE.findall(haystack)))
        is_security = bool(self._SECURITY_RE.search(haystack))

        # 1. Category Classification
        if not body:
            category = "empty"
        elif is_security:
            category = "security"
        elif local in self.AUTOMATED_LOCALPARTS:
            category = "automated"
        else:
            category = "actionable"

        # 2. Intent Priority Routing
        if category == "security":
            intent = "security_notification"
        elif category == "automated":
            intent = "automated_notification"
        elif category == "empty":
            intent = "none"
        # A clear "no" always wins, even over a meeting/price phrase that
        # might also appear in the same message (e.g. "not interested in
        # a call right now").
        elif self._matches(self.DISENGAGEMENT_PATTERNS, haystack):
            intent = "not_interested"
        elif self._matches(self.MEETING_PATTERNS, haystack):
            intent = "meeting_request"
        # Approval must be checked before price: trucking-industry phrases
        # like "approve this rate confirmation" contain the word "rate"
        # and would otherwise be misclassified as a pricing question.
        elif self._matches(self.APPROVAL_PATTERNS, haystack):
            intent = "approval_request"
        # Check for price requests before general information requests.
        # Exact keyword match first, then a typo-tolerant fuzzy check
        # (catches things like "chages" for "charges").
        elif self._matches(self.PRICE_PATTERNS, haystack) or self._fuzzy_matches_price(haystack):
            intent = "price_request"
        elif self._matches(self.INFORMATION_PATTERNS, haystack):
            intent = "information_request"
        elif self._matches(self.FOLLOW_UP_PATTERNS, haystack):
            intent = "follow_up"
        elif "?" in body or self._QUESTION_WORD_RE.match(body.strip()):
            # Either a literal question mark, or the message starts with a
            # question word/auxiliary verb (covers casual texting style
            # like "are u available" or "what are the charges" with no "?").
            intent = "question"
        else:
            intent = "general_request"

        # 3. Attributes
        urgency = "high" if (category == "security" or urgency_hits) else "normal"
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

        if analysis["category"] == "security":
            message_id = message.get("message_id") or message.get("id") or "unknown"
            return f"security:{message_id}"

        subject = analysis["subject"].lower()
        sender = cls._sender(message)
        normalized_subject = re.sub(r"\s+", " ", subject)

        if not normalized_subject:
            return f"{sender}|no-subject"

        return f"{sender}|{normalized_subject}"
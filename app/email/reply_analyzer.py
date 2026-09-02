"""
ReplyAnalyzer: turns a raw recipient reply into structured, explainable data.

Deterministic, rule/regex based — same philosophy as the rest of the agent
(EmailAnalyzer, DecisionEngine): no black-box classification. Every field
on the returned analysis can be traced back to a matched pattern, and the
analysis carries a confidence score so the decision layer can gate
auto-learning on it (see DecisionEngine.decide_on_reply / Phase 6).

This is deliberately separate from app.email.understanding.EmailUnderstanding,
which triages a general inbox (security alerts, automated notices, etc).
This module is purpose-built for replies to *our own* cold outreach emails
and uses a sales-reply intent taxonomy instead.
"""
from __future__ import annotations

import re

INTENTS = (
    "interested",
    "not_interested",
    "question",
    "request_information",
    "meeting_request",
    "call_request",
    "price_request",
    "follow_up",
    "unsubscribe",
    "neutral",
    "unknown",
)

SENTIMENTS = ("positive", "negative", "neutral", "mixed")

OUTCOMES = (
    "positive",
    "negative",
    "needs_follow_up",
    "no_opportunity",
    "conversion",
    "unknown",
)

INTEREST_LEVELS = ("high", "medium", "low", "none", "unknown")


# Ordered: first matching rule wins for INTENT. Order encodes priority,
# e.g. an unsubscribe request always wins over a stray question mark.
_UNSUBSCRIBE_PATTERNS = (
    r"\bunsubscribe\b",
    r"\bremove me\b",
    r"\btake me off\b",
    r"\bstop (?:emailing|contacting|messaging) me\b",
    r"\bdo not (?:email|contact) me again\b",
)

_NOT_INTERESTED_PATTERNS = (
    r"\bnot interested\b",
    r"\bno thanks?\b",
    r"\bno thank you\b",
    r"\bwe(?:'| a)re all set\b",
    r"\balready (?:have|working with|use) (?:a|an|our) (?:dispatcher|dispatch|broker)\b",
    r"\bnot (?:looking|in the market)\b",
    r"\bplease (?:remove|don't contact)\b",
)

_MEETING_PATTERNS = (
    r"\b(?:schedule|book|arrange|set up)\b.{0,60}\b(?:call|meeting|demo|chat)\b",
    r"\b(?:can|could|would)\s+we\s+(?:hop on|have)\b.{0,40}\b(?:call|meeting)\b",
    r"\bavailable\b.{0,60}\b(?:call|meeting)\b",
    r"\blet'?s (?:talk|chat|connect|hop on a call)\b",
)

_CALL_PATTERNS = (
    r"\bcall me\b",
    r"\bgive me a call\b",
    r"\bphone (?:number|call)\b",
    r"\breach me at\b.{0,20}\d",
)

_PRICE_PATTERNS = (
    r"\b(?:price|pricing|rate|rates|cost|fee|fees|percentage|commission)\b",
    r"\bhow much\b",
    r"\bwhat do you charge\b",
)

_INFO_REQUEST_PATTERNS = (
    r"\b(?:send|share|provide)\b.{0,60}\b(?:details|information|info|brochure|more)\b",
    r"\bcan you (?:send|tell me more|explain)\b",
    r"\bwhat exactly do you\b",
)

_INTERESTED_PATTERNS = (
    r"\binterested\b",
    r"\bsounds good\b",
    r"\btell me more\b",
    r"\blet'?s do (?:it|this)\b",
    r"\bi'?d like to\b",
    r"\bsign (?:me |us )?up\b",
)

_FOLLOW_UP_PATTERNS = (
    r"\bfollow(?:ing)? up\b",
    r"\bcircling back\b",
    r"\bcheck(?:ing)? (?:back|in) (?:next|in a)\b",
    r"\bnot right now,? but\b",
    r"\bmaybe (?:next|later|in a few)\b",
    r"\btry (?:me |us )?again\b",
)

_POSITIVE_WORDS = (
    "great", "sounds good", "interested", "thanks", "appreciate", "perfect",
    "awesome", "yes", "sure", "definitely", "would love", "looking forward",
)

_NEGATIVE_WORDS = (
    "not interested", "no thanks", "stop", "unsubscribe", "annoyed",
    "already have", "not looking", "too expensive", "not a fit", "no.",
)

_OBJECTION_PATTERNS = {
    "price": _PRICE_PATTERNS + (r"\btoo expensive\b", r"\bcan'?t afford\b"),
    "already_has_provider": (r"\balready (?:have|working with|use) (?:a|an|our)\b",),
    "bad_timing": (r"\bnot (?:right )?now\b", r"\bnot the right time\b", r"\bmaybe (?:later|next)\b"),
    "trust": (r"\bhow do i know\b", r"\bwho are you\b", r"\bis this legit\b", r"\bscam\b"),
    "no_need": (r"\bdon'?t need\b", r"\bnot looking for\b"),
}


def _find(patterns, text):
    for pattern in patterns:
        if re.search(pattern, text, re.I | re.S):
            return True
    return False


def _find_objection(text):
    for label, patterns in _OBJECTION_PATTERNS.items():
        if _find(patterns, text):
            return label
    return ""


class ReplyAnalyzer:
    """Analyzes a raw reply body (+ optional subject) into structured data.

    Usage:
        analysis = ReplyAnalyzer().analyze(body, subject="Re: ...")
    """

    def analyze(self, body: str, subject: str = "") -> dict:
        body = (body or "").strip()
        subject = (subject or "").strip()
        haystack = f"{subject}\n{body}".lower()

        if not body:
            return self._result(
                intent="unknown", sentiment="neutral", interest_level="unknown",
                objection="", question="", requested_action="", urgency="normal",
                topic="", outcome="unknown", confidence=0.0,
                reason="empty reply body",
            )

        # -----------------------------------------------------------
        # Intent (priority-ordered; first match wins)
        # -----------------------------------------------------------
        if _find(_UNSUBSCRIBE_PATTERNS, haystack):
            intent, reason = "unsubscribe", "unsubscribe/opt-out language detected"
        elif _find(_NOT_INTERESTED_PATTERNS, haystack):
            intent, reason = "not_interested", "explicit disinterest language detected"
        elif _find(_MEETING_PATTERNS, haystack):
            intent, reason = "meeting_request", "meeting/call scheduling language detected"
        elif _find(_CALL_PATTERNS, haystack):
            intent, reason = "call_request", "phone call request detected"
        elif _find(_PRICE_PATTERNS, haystack):
            intent, reason = "price_request", "pricing/cost question detected"
        elif _find(_INFO_REQUEST_PATTERNS, haystack):
            intent, reason = "request_information", "request for more information detected"
        elif _find(_INTERESTED_PATTERNS, haystack):
            intent, reason = "interested", "positive interest language detected"
        elif _find(_FOLLOW_UP_PATTERNS, haystack):
            intent, reason = "follow_up", "deferred/follow-up-later language detected"
        elif "?" in body:
            intent, reason = "question", "reply contains a question with no other matched intent"
        else:
            intent, reason = "neutral", "no strong intent signal matched"

        # -----------------------------------------------------------
        # Sentiment
        # -----------------------------------------------------------
        pos_hits = sum(1 for w in _POSITIVE_WORDS if w in haystack)
        neg_hits = sum(1 for w in _NEGATIVE_WORDS if w in haystack)
        if pos_hits and neg_hits:
            sentiment = "mixed"
        elif pos_hits and not neg_hits:
            sentiment = "positive"
        elif neg_hits and not pos_hits:
            sentiment = "negative"
        else:
            sentiment = "neutral"

        # -----------------------------------------------------------
        # Interest level
        # -----------------------------------------------------------
        if intent in ("interested", "meeting_request", "call_request"):
            interest_level = "high"
        elif intent in ("price_request", "request_information", "question"):
            interest_level = "medium"
        elif intent in ("follow_up",):
            interest_level = "low"
        elif intent in ("not_interested", "unsubscribe"):
            interest_level = "none"
        else:
            interest_level = "unknown"

        # -----------------------------------------------------------
        # Objection / question / requested action / urgency / topic
        # -----------------------------------------------------------
        objection = _find_objection(haystack) if intent in (
            "not_interested", "price_request", "follow_up",
        ) else ""

        question = ""
        if "?" in body:
            # first sentence ending in '?' — capped length, no invention
            match = re.search(r"([^.?!]{3,200}\?)", body)
            question = match.group(1).strip() if match else ""

        requested_action = ""
        match = re.search(
            r"\b(?:can|could|would)\s+you\s+(.{3,120}?)(?:[?.]|$)", body, re.I,
        )
        if match:
            requested_action = match.group(1).strip()

        urgent_terms = ("urgent", "asap", "today", "immediately", "right away")
        urgency = "high" if any(t in haystack for t in urgent_terms) else "normal"

        topic = intent  # explainable, coarse topic label derived from intent

        # -----------------------------------------------------------
        # Outcome (what this reply means for the lead relationship)
        # -----------------------------------------------------------
        if intent in ("interested", "meeting_request", "call_request"):
            outcome = "positive"
        elif intent in ("price_request", "request_information", "question"):
            outcome = "needs_follow_up"
        elif intent == "follow_up":
            outcome = "needs_follow_up"
        elif intent in ("not_interested",):
            outcome = "negative"
        elif intent == "unsubscribe":
            outcome = "no_opportunity"
        else:
            outcome = "unknown"

        # -----------------------------------------------------------
        # Confidence: how sure are we in this classification?
        # Explainable, not a black box — based on how strong/unique the match was.
        # -----------------------------------------------------------
        if intent in ("unsubscribe", "not_interested", "meeting_request", "call_request", "interested"):
            confidence = 0.9
        elif intent in ("price_request", "request_information", "follow_up"):
            confidence = 0.7
        elif intent == "question":
            confidence = 0.5
        else:
            confidence = 0.3

        return self._result(
            intent=intent, sentiment=sentiment, interest_level=interest_level,
            objection=objection, question=question, requested_action=requested_action,
            urgency=urgency, topic=topic, outcome=outcome, confidence=confidence,
            reason=reason,
        )

    @staticmethod
    def _result(intent, sentiment, interest_level, objection, question,
                requested_action, urgency, topic, outcome, confidence, reason):
        assert intent in INTENTS, intent
        assert sentiment in SENTIMENTS, sentiment
        assert outcome in OUTCOMES, outcome
        assert interest_level in INTEREST_LEVELS, interest_level
        return {
            "intent": intent,
            "sentiment": sentiment,
            "interest_level": interest_level,
            "objection": objection,
            "question": question,
            "requested_action": requested_action,
            "urgency": urgency,
            "topic": topic,
            "outcome": outcome,
            "confidence": confidence,
            "reason": reason,
        }

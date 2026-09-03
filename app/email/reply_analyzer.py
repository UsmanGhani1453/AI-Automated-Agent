from __future__ import annotations
import re
from typing import Dict, Any, List

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

# --- PATTERNS ---
_UNSUBSCRIBE_PATTERNS = (
    r"\bunsubscribe\b", r"\bremove me\b", r"\btake me off\b",
    r"\bstop (?:emailing|contacting|messaging) me\b",
    r"\bdo not (?:email|contact) me again\b",
)
_NOT_INTERESTED_PATTERNS = (
    r"\bnot interested\b", r"\bno thanks?\b", r"\bno thank you\b",
    r"\bwe(?:'| a)re all set\b", r"\bnot (?:looking|in the market)\b",
    r"\balready (?:have|working with|use) (?:a|an|our)\b",
    r"\bplease (?:remove|don't contact)\b",
)
_MEETING_PATTERNS = (
    r"\b(?:schedule|book|arrange|set up)\b.{0,60}\b(?:call|meeting|demo|chat)\b",
    r"\b(?:can|could|would)\s+we\s+(?:hop on|have)\b.{0,40}\b(?:call|meeting)\b",
    r"\bavailable\b.{0,60}\b(?:call|meeting)\b",
    r"\blet'?s (?:talk|chat|connect|hop on a call)\b",
)
_CALL_PATTERNS = (
    r"\bcall me\b", r"\bgive me a call\b", r"\bphone (?:number|call)\b",
    r"\breach me at\b.{0,20}\d",
)
_PRICE_PATTERNS = (
    r"\b(?:price|pricing|rate|rates|cost|fee|fees|percentage|commission)\b",
    r"\bhow much\b", r"\bwhat do you charge\b",
)
_INFO_REQUEST_PATTERNS = (
    r"\b(?:send|share|provide)\b.{0,60}\b(?:details|information|info|brochure|more)\b",
    r"\bcan you (?:send|tell me more|explain)\b", r"\bwhat exactly do you\b",
)
_INTERESTED_PATTERNS = (
    r"\binterested\b", r"\bsounds good\b", r"\btell me more\b",
    r"\blet'?s do (?:it|this)\b", r"\bi'?d like to\b", r"\bsign (?:me |us )?up\b",
)
_FOLLOW_UP_PATTERNS = (
    r"\bfollow(?:ing)? up\b", r"\bcircling back\b",
    r"\bcheck(?:ing)? (?:back|in) (?:next|in a)\b", r"\bnot right now,? but\b",
    r"\bmaybe (?:next|later|in a few)\b", r"\btry (?:me |us )?again\b",
)

# --- COMPILED SENTIMENT REGEX ---
_POSITIVE_WORDS = (
    "great", "sounds good", "interested", "thanks", "appreciate", "perfect",
    "awesome", "yes", "sure", "definitely", "would love", "looking forward",
)
_NEGATIVE_WORDS = (
    "not interested", "no thanks", "stop", "unsubscribe", "annoyed",
    "already have", "not looking", "too expensive", "not a fit", "no",
)

_POSITIVE_RE = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in _POSITIVE_WORDS) + r")\b", re.I)
_NEGATIVE_RE = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in _NEGATIVE_WORDS) + r")\b", re.I)

_OBJECTION_PATTERNS = {
    "price": _PRICE_PATTERNS + (r"\btoo expensive\b", r"\bcan'?t afford\b"),
    "already_has_provider": (r"\balready (?:have|working with|use) (?:a|an|our)\b",),
    "bad_timing": (r"\bnot (?:right )?now\b", r"\bnot the right time\b", r"\bmaybe (?:later|next)\b"),
    "trust": (r"\bhow do i know\b", r"\bwho are you\b", r"\bis this legit\b", r"\bscam\b"),
    "no_need": (r"\bdon'?t need\b", r"\bnot looking for\b"),
}


def _find(patterns: tuple, text: str) -> bool:
    for pattern in patterns:
        if re.search(pattern, text, re.I | re.S):
            return True
    return False


def _find_objection(text: str) -> str:
    for label, patterns in _OBJECTION_PATTERNS.items():
        if _find(patterns, text):
            return label
    return ""


class ReplyAnalyzer:
    """Analyzes a raw email reply body (+ optional subject) into structured data."""

    def analyze(self, body: str, subject: str = "") -> Dict[str, Any]:
        body = (body or "").strip()
        subject = (subject or "").strip()
        haystack = f"{subject}\n{body}".lower()

        if not body:
            return self._result(
                intent="unknown", all_intents=["unknown"], sentiment="neutral",
                interest_level="unknown", objection="", question="",
                requested_action="", urgency="normal", topic="",
                outcome="unknown", confidence=0.0, reason="empty reply body"
            )

        # 1. Multi-Intent Detection
        matched_intents = []
        if _find(_UNSUBSCRIBE_PATTERNS, haystack): matched_intents.append("unsubscribe")
        if _find(_NOT_INTERESTED_PATTERNS, haystack): matched_intents.append("not_interested")
        if _find(_MEETING_PATTERNS, haystack): matched_intents.append("meeting_request")
        if _find(_CALL_PATTERNS, haystack): matched_intents.append("call_request")
        if _find(_PRICE_PATTERNS, haystack): matched_intents.append("price_request")
        if _find(_INFO_REQUEST_PATTERNS, haystack): matched_intents.append("request_information")
        if _find(_INTERESTED_PATTERNS, haystack): matched_intents.append("interested")
        if _find(_FOLLOW_UP_PATTERNS, haystack): matched_intents.append("follow_up")
        
        has_question = "?" in body
        if has_question and "question" not in matched_intents:
            matched_intents.append("question")

        if not matched_intents:
            matched_intents.append("neutral")

        # Primary intent is the highest priority match
        primary_intent = matched_intents[0]

        # 2. Robust Sentiment Analysis
        pos_hits = len(_POSITIVE_RE.findall(haystack))
        neg_hits = len(_NEGATIVE_RE.findall(haystack))
        
        if pos_hits > 0 and neg_hits > 0:
            sentiment = "mixed"
        elif pos_hits > 0:
            sentiment = "positive"
        elif neg_hits > 0:
            sentiment = "negative"
        else:
            sentiment = "neutral"

        # 3. Interest Level Mapping
        if primary_intent in ("interested", "meeting_request", "call_request"):
            interest_level = "high"
        elif primary_intent in ("price_request", "request_information", "question"):
            interest_level = "medium"
        elif primary_intent == "follow_up":
            interest_level = "low"
        elif primary_intent in ("not_interested", "unsubscribe"):
            interest_level = "none"
        else:
            interest_level = "unknown"

        # 4. Extractions
        objection = _find_objection(haystack) if primary_intent in (
            "not_interested", "price_request", "follow_up"
        ) else ""

        question = ""
        if has_question:
            match = re.search(r"([^.?!]{3,200}\?)", body)
            question = match.group(1).strip() if match else ""

        requested_action = ""
        action_match = re.search(r"\b(?:can|could|would)\s+you\s+(.{3,120}?)(?:[?.]|$)", body, re.I)
        if action_match:
            requested_action = action_match.group(1).strip()

        urgent_terms = ("urgent", "asap", "today", "immediately", "right away")
        urgency = "high" if any(t in haystack for t in urgent_terms) else "normal"

        # 5. Outcome & Confidence
        if primary_intent in ("interested", "meeting_request", "call_request"):
            outcome = "positive"
        elif primary_intent in ("price_request", "request_information", "question", "follow_up"):
            outcome = "needs_follow_up"
        elif primary_intent == "not_interested":
            outcome = "negative"
        elif primary_intent == "unsubscribe":
            outcome = "no_opportunity"
        else:
            outcome = "unknown"

        confidence_map = {
            "unsubscribe": 0.95, "not_interested": 0.9, "meeting_request": 0.9,
            "call_request": 0.9, "interested": 0.85, "price_request": 0.8,
            "request_information": 0.8, "follow_up": 0.75, "question": 0.6,
            "neutral": 0.4, "unknown": 0.1
        }
        confidence = confidence_map.get(primary_intent, 0.5)
        reason = f"Matched primary intent: {primary_intent}. Full intents detected: {', '.join(matched_intents)}."

        return self._result(
            intent=primary_intent,
            all_intents=matched_intents,
            sentiment=sentiment,
            interest_level=interest_level,
            objection=objection,
            question=question,
            requested_action=requested_action,
            urgency=urgency,
            topic=primary_intent,
            outcome=outcome,
            confidence=confidence,
            reason=reason,
        )

    @staticmethod
    def _result(intent: str, all_intents: List[str], sentiment: str, interest_level: str,
                objection: str, question: str, requested_action: str, urgency: str,
                topic: str, outcome: str, confidence: float, reason: str) -> Dict[str, Any]:
        
        assert intent in INTENTS, f"Invalid intent: {intent}"
        assert sentiment in SENTIMENTS, f"Invalid sentiment: {sentiment}"
        assert outcome in OUTCOMES, f"Invalid outcome: {outcome}"
        assert interest_level in INTEREST_LEVELS, f"Invalid interest level: {interest_level}"
        
        return {
            "intent": intent,
            "all_intents": all_intents,
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
"""
Personal writing preference learner.

Compares an AI draft with the user's edited version and extracts
explainable, reusable writing preferences.
"""
from __future__ import annotations

import re

from app.learning.pattern_scorer import PatternScorer


def _word_count(text: str) -> int:
    return len(text.split())


def _has_exclamation(text: str) -> bool:
    return "!" in text


def _nonempty_lines(text: str) -> list[str]:
    return [line.strip() for line in text.strip().splitlines() if line.strip()]


def _first_line(text: str) -> str:
    lines = _nonempty_lines(text)
    return lines[0] if lines else ""


def _last_lines(text: str) -> str:
    lines = _nonempty_lines(text)
    return "\n".join(lines[-4:]) if lines else ""


def _greeting_style(text: str) -> str | None:
    first = _first_line(text).lower()

    if re.match(r"^(hi|hello|hey)\b", first):
        return "casual"

    if re.match(r"^dear\b", first):
        return "formal"

    return None


def _has_formal_signoff(text: str) -> bool:
    lower = text.lower()
    return any(
        phrase in lower
        for phrase in (
            "best regards",
            "kind regards",
            "sincerely",
            "yours sincerely",
        )
    )


def _has_casual_signoff(text: str) -> bool:
    lower = text.lower()
    return any(
        phrase in lower
        for phrase in (
            "thanks,",
            "thanks",
            "best,",
            "cheers,",
        )
    )


class PreferenceLearner:
    def __init__(self):
        self.scorer = PatternScorer()

    def learn_from_edit(self, ai_email: str, user_email: str):
        findings = []

        ai_wc = _word_count(ai_email)
        user_wc = _word_count(user_email)

        # ---------------------------------------------------------
        # Length
        # ---------------------------------------------------------
        if ai_wc > 0:
            ratio = (ai_wc - user_wc) / ai_wc

            if ratio > 0.20:
                findings.append({
                    "key": "prefers_shorter_emails",
                    "description": "User prefers shorter emails than the AI draft.",
                    "positive": True,
                })

            elif ratio < -0.20:
                findings.append({
                    "key": "prefers_detailed_emails",
                    "description": "User prefers more detailed emails than the AI draft.",
                    "positive": True,
                })

        # ---------------------------------------------------------
        # Greeting
        # ---------------------------------------------------------
        ai_greeting = _greeting_style(ai_email)
        user_greeting = _greeting_style(user_email)

        if ai_greeting and user_greeting:
            if ai_greeting != user_greeting:
                findings.append({
                    "key": f"prefers_{user_greeting}_greeting",
                    "description": (
                        f"User prefers {user_greeting} greetings "
                        "over the AI's original greeting style."
                    ),
                    "positive": True,
                })

                if ai_greeting == "formal" and user_greeting == "casual":
                    findings.append({
                        "key": "dislikes_formal_greeting",
                        "description": (
                            "User tends to replace formal greetings "
                            "with more casual greetings."
                        ),
                        "positive": True,
                    })

        elif ai_greeting and not user_greeting:
            findings.append({
                "key": "prefers_direct_opening",
                "description": "User tends to remove the AI's greeting and open directly.",
                "positive": True,
            })

        # ---------------------------------------------------------
        # Exclamation / energy
        # ---------------------------------------------------------
        if _has_exclamation(ai_email) and not _has_exclamation(user_email):
            findings.append({
                "key": "prefers_no_exclamation",
                "description": "User removes exclamation marks and high-energy punctuation.",
                "positive": True,
            })

        elif not _has_exclamation(ai_email) and _has_exclamation(user_email):
            findings.append({
                "key": "allows_exclamation",
                "description": "User sometimes adds exclamation marks to drafts.",
                "positive": True,
            })

        # ---------------------------------------------------------
        # Formality / sign-off
        # ---------------------------------------------------------
        ai_formal = _has_formal_signoff(ai_email)
        user_formal = _has_formal_signoff(user_email)

        ai_casual = _has_casual_signoff(ai_email)
        user_casual = _has_casual_signoff(user_email)

        if ai_formal and user_casual:
            findings.append({
                "key": "prefers_casual_signoff",
                "description": "User prefers a more casual sign-off.",
                "positive": True,
            })

        elif ai_casual and user_formal:
            findings.append({
                "key": "prefers_formal_signoff",
                "description": "User prefers a more formal sign-off.",
                "positive": True,
            })

        # ---------------------------------------------------------
        # Aggressive language
        # ---------------------------------------------------------
        aggressive_markers = {
            "act now",
            "don't miss",
            "limited time",
            "hurry",
            "urgent",
        }

        ai_lower = ai_email.lower()
        user_lower = user_email.lower()

        if any(
            marker in ai_lower and marker not in user_lower
            for marker in aggressive_markers
        ):
            findings.append({
                "key": "dislikes_aggressive_cta",
                "description": "User removes aggressive or urgency-driven CTA language.",
                "positive": True,
            })

        # ---------------------------------------------------------
        # Directness
        # ---------------------------------------------------------
        ai_first = _first_line(ai_email)
        user_first = _first_line(user_email)

        if ai_first and user_first and ai_first != user_first:
            if len(user_first.split()) < len(ai_first.split()):
                findings.append({
                    "key": "prefers_direct_openings",
                    "description": "User tends to make email openings more direct.",
                    "positive": True,
                })

        # ---------------------------------------------------------
        # Persist all findings
        # ---------------------------------------------------------
        for finding in findings:
            self.scorer.record_preference_signal(
                finding["key"],
                finding["description"],
                finding["positive"],
            )

        return findings
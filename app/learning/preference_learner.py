"""
Preference learner: compares the AI-generated email against the user's
edited version and extracts simple, explainable structural preferences
(length, greeting removed, CTA softened, etc). Purely statistical/rule-based
text diffing — no LLM needed for this.
"""
import re
from app.learning.pattern_scorer import PatternScorer


def _word_count(text):
    return len(text.split())


def _has_exclamation(text):
    return "!" in text


def _greeting_line(text):
    lines = [l for l in text.strip().splitlines() if l.strip()]
    return lines[0] if lines else ""


class PreferenceLearner:
    def __init__(self):
        self.scorer = PatternScorer()

    def learn_from_edit(self, ai_email: str, user_email: str):
        """Returns a list of {key, description, positive} findings and records them."""
        findings = []

        ai_wc, user_wc = _word_count(ai_email), _word_count(user_email)
        if ai_wc > 0:
            shrink_ratio = (ai_wc - user_wc) / ai_wc
            if shrink_ratio > 0.25:
                findings.append({
                    "key": "prefers_shorter_emails",
                    "description": "User prefers shorter emails than the AI's first draft.",
                    "positive": True,
                })
            elif shrink_ratio < -0.25:
                findings.append({
                    "key": "prefers_shorter_emails",
                    "description": "User prefers shorter emails than the AI's first draft.",
                    "positive": False,
                })

        ai_greet, user_greet = _greeting_line(ai_email), _greeting_line(user_email)
        if ai_greet and ai_greet not in user_email:
            findings.append({
                "key": "dislikes_formal_greeting",
                "description": "User tends to rewrite or remove the AI's opening greeting.",
                "positive": True,
            })

        if _has_exclamation(ai_email) and not _has_exclamation(user_email):
            findings.append({
                "key": "prefers_no_exclamation",
                "description": "User removes exclamation marks / high-energy tone.",
                "positive": True,
            })

        # Aggressive CTA phrases the user tends to strip out
        aggressive_markers = ["act now", "don't miss", "limited time", "hurry", "urgent"]
        for marker in aggressive_markers:
            if marker in ai_email.lower() and marker not in user_email.lower():
                findings.append({
                    "key": "dislikes_aggressive_cta",
                    "description": "User removes aggressive/urgency-driven CTA language.",
                    "positive": True,
                })
                break

        for f in findings:
            self.scorer.record_preference_signal(f["key"], f["description"], f["positive"])

        return findings

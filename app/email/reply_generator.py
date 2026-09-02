"""
Context-aware reply generation for the adaptive email agent.

The generator is intentionally model-free for now. It combines:
- deterministic email understanding
- conversation context
- learned personal writing preferences
- explicit uncertainty handling

No facts are invented.
"""

from __future__ import annotations

import re
from email.utils import parseaddr

from app.database.repository import PreferenceRepository
from app.email.understanding import EmailUnderstanding


class ReplyGenerator:
    PROMO_TERMS = {
        "unsubscribe",
        "newsletter",
        "prize pool",
        "limited time",
        "special offer",
        "sale",
        "discount",
        "deal",
        "promotion",
        "marketing",
        # Spanish equivalents (subscription mgmt / marketing copy)
        "darte de baja",
        "dejar de recibir",
        "gestionar tus suscripciones",
        "gestionar tu suscripción",
        "cancelar suscripción",
        "tienda online",
        "descuento",
        "código promocional",
    }

    # Sender-domain fragments that indicate bulk/marketing senders
    # even when the local part looks like a "real" account.
    PROMO_DOMAIN_HINTS = (
        "-free.",
        "mailer.",
        "mailing.",
        "newsletter.",
        "email.",
        "campaign.",
        "marketing.",
    )

    def __init__(self, sender_info=None):
        self.sender_info = sender_info or {}
        self.understanding = EmailUnderstanding()
        self.preferences = PreferenceRepository

    # ------------------------------------------------------------------
    # Basic helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _first_name(from_header: str) -> str:
        name, address = parseaddr(from_header or "")

        if name:
            return name.split()[0]

        if address and "@" in address:
            return (
                address.split("@", 1)[0]
                .replace(".", " ")
                .split()[0]
                .title()
            )

        return "there"

    @staticmethod
    def _clean_subject(subject: str) -> str:
        return re.sub(
            r"^(?:(?:re|fw|fwd):\s*)+",
            "",
            subject or "",
            flags=re.I,
        ).strip()

    # ------------------------------------------------------------------
    # Learned preferences
    # ------------------------------------------------------------------

    def _preference_confidence(self, key: str) -> float:
        """
        Return the learned confidence for a preference.

        Confidence is stored in SQLite and ranges from 0.0 to 1.0.
        """
        rows = self.preferences.all()

        for row in rows:
            if row["preference_key"] == key:
                return float(row["confidence"])

        return 0.0

    def _choose_greeting(self, first_name: str) -> str:
        """
        Choose a greeting based on learned user preferences.
        """
        casual = self._preference_confidence(
            "prefers_casual_greeting"
        )

        formal = self._preference_confidence(
            "prefers_formal_greeting"
        )

        direct = self._preference_confidence(
            "prefers_direct_opening"
        )

        # Strong evidence that the user prefers no greeting.
        if direct >= 0.65:
            return ""

        # Stronger formal preference.
        if formal > casual and formal >= 0.60:
            return f"Hello {first_name},"

        # Default.
        return f"Hi {first_name},"

    def _choose_signoff(self) -> str:
        """
        Choose a sign-off based on learned preferences.
        """
        formal = self._preference_confidence(
            "prefers_formal_signoff"
        )

        casual = self._preference_confidence(
            "prefers_casual_signoff"
        )

        sender_name = self.sender_info.get(
            "sender_name",
            "",
        )

        sender_title = self.sender_info.get(
            "sender_title",
            "",
        )

        if formal > casual and formal >= 0.60:
            return (
                "Best regards,\n"
                f"{sender_name}\n"
                f"{sender_title}"
            )

        return (
            "Thanks,\n"
            f"{sender_name}\n"
            f"{sender_title}"
        )

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def classify(self, message: dict):
        """
        Classify an incoming email into a safe high-level category.
        """
        analysis = self.understanding.analyze(message)

        if analysis["category"] == "security":
            return (
                "security",
                "security/account notification",
            )

        if analysis["category"] == "automated":
            return (
                "automated",
                "sender address indicates automated mail",
            )

        subject = (
            message.get("subject") or ""
        ).lower()

        body = (
            message.get("body") or ""
        ).lower()

        haystack = f"{subject}\n{body}"

        sender_domain = analysis.get(
            "sender_email", ""
        ).split("@", 1)[-1]

        if (
            any(
                term in haystack
                for term in self.PROMO_TERMS
            )
            or any(
                hint in sender_domain
                for hint in self.PROMO_DOMAIN_HINTS
            )
        ):
            return (
                "promotional",
                "newsletter or promotional content",
            )

        if analysis["category"] == "empty":
            return (
                "empty",
                "no readable message body",
            )

        return (
            "actionable",
            "likely human/actionable message",
        )

    # ------------------------------------------------------------------
    # Intent-specific wording
    # ------------------------------------------------------------------

    def _opening_for_intent(self, analysis: dict) -> str:
        intent = analysis["intent"]

        if intent == "meeting_request":
            return (
                "Thanks for reaching out. "
                "I’ve noted your request for a quick call."
            )

        if intent == "information_request":
            return (
                "Thanks for reaching out. "
                "I’ve noted your request for the information."
            )

        if intent == "approval_request":
            return (
                "Thanks for sending this over. "
                "I’ve reviewed the request."
            )

        if intent == "follow_up":
            return (
                "Thanks for following up. "
                "I’ve got your message."
            )

        if intent == "question":
            return (
                "Thanks for your message. "
                "I understand your question."
            )

        return "Thanks for reaching out."

    def _next_step_for_intent(
        self,
        analysis: dict,
    ) -> str:
        """
        Generate the next-step sentence without inventing
        facts that the agent does not know.
        """
        intent = analysis["intent"]

        if intent == "meeting_request":
            time_reference = analysis.get(
                "time_reference"
            )

            if time_reference:
                return (
                    f"I’ve noted the {time_reference} timing. "
                    "I’ll confirm the exact availability "
                    "before sending a final confirmation."
                )

            return (
                "I’ll confirm the timing before sending "
                "a final confirmation."
            )

        if intent == "information_request":
            return (
                "I’ll review the request and send "
                "the relevant details shortly."
            )

        if intent == "approval_request":
            return (
                "I’ll review the request and confirm "
                "the approval status shortly."
            )

        if intent == "follow_up":
            return (
                "I’ll follow up with the next steps shortly."
            )

        if analysis["urgency"] == "high":
            return (
                "I’ll prioritize this and get back "
                "to you shortly."
            )

        if intent == "question":
            return (
                "I’ll review the question and get back "
                "to you with the relevant details."
            )

        return (
            "I’ll review this and get back to you "
            "with the next steps."
        )

    # ------------------------------------------------------------------
    # Draft generation
    # ------------------------------------------------------------------

    def draft(
        self,
        message: dict,
        conversation_context=None,
    ) -> dict:
        """
        Generate a contextual draft.

        The function never assumes unavailable facts such as:
        - calendar availability
        - pricing
        - approval status
        - whether the user agrees with a request
        """
        category, reason = self.classify(message)

        subject = self._clean_subject(
            message.get("subject", "")
        )

        analysis = self.understanding.analyze(
            message
        )

        # --------------------------------------------------------------
        # Non-actionable mail
        # --------------------------------------------------------------
        if category != "actionable":
            return {
                "category": category,
                "reason": reason,
                "subject": subject,
                "body": "",
                "should_reply": False,
                "analysis": analysis,
                "requires_human_decision": False,
            }

        # --------------------------------------------------------------
        # Conversation context
        # --------------------------------------------------------------
        context = conversation_context or {}

        messages = context.get(
            "messages",
            [],
        )

        prior_count = max(
            0,
            len(messages) - 1,
        )

        # --------------------------------------------------------------
        # Sender identity
        # --------------------------------------------------------------
        first_name = self._first_name(
            message.get("from", "")
        )

        # --------------------------------------------------------------
        # Intent-specific content
        # --------------------------------------------------------------
        opening = self._opening_for_intent(
            analysis
        )

        next_step = self._next_step_for_intent(
            analysis
        )

        # --------------------------------------------------------------
        # Greeting
        # --------------------------------------------------------------
        greeting = self._choose_greeting(
            first_name
        )

        body_parts = []

        if greeting:
            body_parts.extend(
                [
                    greeting,
                    "",
                ]
            )

        body_parts.extend(
            [
                opening,
                "",
                next_step,
                "",
                self._choose_signoff(),
            ]
        )

        body = "\n".join(
            body_parts
        ).strip()

        # --------------------------------------------------------------
        # Human decision detection
        # --------------------------------------------------------------
        requires_human_decision = analysis[
            "intent"
        ] in {
            "meeting_request",
            "approval_request",
        }

        return {
            "category": category,
            "reason": reason,
            "subject": (
                f"Re: {subject}"
                if subject
                else "Re:"
            ),
            "body": body,
            "should_reply": True,
            "analysis": analysis,
            "conversation": {
                "prior_message_count": prior_count,
                "thread_key": context.get(
                    "thread_key"
                ),
            },
            "requires_human_decision": (
                requires_human_decision
            ),
        }
        
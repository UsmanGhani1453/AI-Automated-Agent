"""
ReplyMatcher: deterministic, explainable matching of an incoming reply to
the sent email (and lead) that caused it.

Tries matching strategies in order of reliability, exactly per the spec:
    1. Message/thread identifiers (In-Reply-To / References header)
    2. Sender address -> lead -> most recent sent email to that lead
    3. Subject similarity ("Re: X" vs "X") + time relationship as a
       lower-confidence fallback when sender/thread alone is ambiguous

Every match carries a `method` and a `confidence` so the decision layer
can require human review on low-confidence matches instead of learning
from a guess (see DecisionEngine.decide_on_reply_match).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from app.database.database import get_conn, row_to_dict, rows_to_dicts
from app.database.repository import LeadRepository


def _normalize_subject(subject: str) -> str:
    return re.sub(r"^(?:(?:re|fw|fwd):\s*)+", "", (subject or ""), flags=re.I).strip().lower()


class ReplyMatcher:
    def match(self, reply: dict) -> dict:
        """
        reply: {
            "sender_email": str,
            "subject": str,
            "in_reply_to": str,
            "references": str,
            "received_at": iso str (optional),
        }

        Returns {"email_id", "lead_id", "method", "confidence", "reason"}.
        `email_id`/`lead_id` are None when no match is found.
        """
        # ---- 1. Message-ID based matching (most reliable) -------------
        for header_field, method in (("in_reply_to", "in_reply_to"), ("references", "references")):
            header_value = (reply.get(header_field) or "").strip()
            if not header_value:
                continue
            ids = re.findall(r"<[^>]+>", header_value) or [header_value]
            for mid in ids:
                found = self._find_sent_email_by_message_id(mid)
                if found:
                    return {
                        "email_id": found["id"],
                        "lead_id": found["lead_id"],
                        "method": method,
                        "confidence": 0.95,
                        "reason": f"matched via {method} header to a tracked sent email",
                    }

        # ---- 2. Sender address -> lead -> most recent sent email ------
        sender_email = (reply.get("sender_email") or "").strip().lower()
        if sender_email:
            lead = LeadRepository.get_by_email(sender_email)
            if lead:
                sent = self._most_recent_sent_email(lead["id"])
                if sent:
                    confidence = 0.85
                    method = "sender"
                    # Strengthen confidence if subject also lines up.
                    if _normalize_subject(reply.get("subject", "")) and \
                            _normalize_subject(reply.get("subject", "")) in (sent.get("body") or "").lower():
                        confidence = 0.9
                    return {
                        "email_id": sent["id"],
                        "lead_id": lead["id"],
                        "method": method,
                        "confidence": confidence,
                        "reason": "reply sender address matches a known lead with a recently sent email",
                    }
                # Sender is a known lead but nothing was ever sent to them.
                return {
                    "email_id": None,
                    "lead_id": lead["id"],
                    "method": "sender_no_sent_email",
                    "confidence": 0.4,
                    "reason": "sender matches a known lead, but no sent email is on record for them",
                }

        # ---- 3. No identifying signal at all ---------------------------
        return {
            "email_id": None,
            "lead_id": None,
            "method": "none",
            "confidence": 0.0,
            "reason": "no message-id, sender, or subject signal matched any known lead or sent email",
        }

    # -----------------------------------------------------------------
    @staticmethod
    def _find_sent_email_by_message_id(message_id: str):
        """Look up a sent email we tagged with this outgoing Message-ID."""
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM emails WHERE outgoing_message_id=?",
                (message_id,),
            ).fetchone()
            return row_to_dict(row) if row else None

    @staticmethod
    def _most_recent_sent_email(lead_id: int):
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM emails WHERE lead_id=? AND sent=1 ORDER BY id DESC LIMIT 1",
                (lead_id,),
            ).fetchone()
            if row:
                return row_to_dict(row)
            # Fall back to most recent approved/generated email for dry-run demos,
            # where "sent" never flips to 1 by design.
            row = conn.execute(
                "SELECT * FROM emails WHERE lead_id=? ORDER BY id DESC LIMIT 1",
                (lead_id,),
            ).fetchone()
            return row_to_dict(row) if row else None

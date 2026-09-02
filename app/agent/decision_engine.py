"""
DecisionEngine: deterministic, explainable decisions per the spec's rule table.
Every decision returns not just an action but the *reason*, so the agent can
always answer "why did you do that?" without needing to ask an LLM to
introspect on itself.
"""
from app.email.validator import EmailValidator
from app.database.repository import SuppressionRepository, LeadRepository

QUALITY_ACCEPT_THRESHOLD = 0.55
RECENT_CONTACT_DAYS = 14

# Phase 6: confidence policy for reply matching/analysis.
# high confidence -> automatic learning
# medium confidence -> flagged for human review, but still tentatively recorded
# low confidence -> rejected outright; never learned from
MATCH_CONFIDENCE_AUTO = 0.75
MATCH_CONFIDENCE_REVIEW = 0.40
ANALYSIS_CONFIDENCE_AUTO = 0.6


class Decision:
    def __init__(self, action, reason, data=None):
        self.action = action
        self.reason = reason
        self.data = data or {}

    def to_dict(self):
        return {"action": self.action, "reason": self.reason, "data": self.data}

    def __repr__(self):
        return f"Decision({self.action!r}, reason={self.reason!r})"


class DecisionEngine:
    def __init__(self):
        self.validator = EmailValidator()

    def decide_on_lead(self, lead: dict) -> Decision:
        valid, reason = self.validator.validate_lead(lead)
        if not valid:
            return Decision("reject_lead", f"lead is invalid: {reason}")

        if SuppressionRepository.is_suppressed(lead["email"]):
            return Decision("do_not_contact", "recipient is on the suppression list")

        lead_id = lead.get("id")
        if lead_id and LeadRepository.recently_contacted(lead_id, days=RECENT_CONTACT_DAYS):
            return Decision("skip", f"recipient was contacted within the last {RECENT_CONTACT_DAYS} days")

        return Decision("proceed", "lead passed validation, suppression, and recency checks")

    def decide_on_memory(self, retrieved_context: dict) -> Decision:
        if retrieved_context.get("similar_episodes"):
            return Decision(
                "use_historical_examples",
                f"{len(retrieved_context['similar_episodes'])} similar past episode(s) found; "
                f"will bias strategy/component selection toward what worked before",
                data={"count": len(retrieved_context["similar_episodes"])},
            )
        return Decision("no_prior_history", "no similar past episodes found; using base learned scores")

    def decide_on_email(self, analyzer_report: dict, attempt: int, max_attempts: int) -> Decision:
        score = analyzer_report.get("quality_score", 0)
        if analyzer_report.get("placeholder_found"):
            if attempt < max_attempts:
                return Decision("regenerate", "unresolved placeholder found in draft", data={"score": score})
            return Decision("require_human_review", "placeholder persisted after max regeneration attempts")

        if score < QUALITY_ACCEPT_THRESHOLD:
            if attempt < max_attempts:
                return Decision(
                    "regenerate",
                    f"quality score {score:.2f} below threshold {QUALITY_ACCEPT_THRESHOLD}",
                    data={"score": score},
                )
            return Decision(
                "require_human_review",
                f"quality score {score:.2f} still below threshold after {max_attempts} attempts",
                data={"score": score},
            )

        return Decision("request_approval", f"quality score {score:.2f} meets threshold", data={"score": score})

    def decide_after_approval(self, approved: bool) -> Decision:
        if approved:
            return Decision("send", "user approved the email")
        return Decision("hold", "user did not approve; email will not be sent")

    # ================================================================
    # PHASE 6: reply match / analysis confidence policy
    # ================================================================

    def decide_on_reply_match(self, match: dict) -> Decision:
        """Gate learning on how confident the reply-to-email match is.

        high confidence  -> auto_learn   (safe to update strategy/pattern scores)
        medium confidence -> require_human_review (record the reply, don't learn yet)
        low confidence    -> reject_match (store raw reply only, no learning, no review queue)
        """
        confidence = match.get("confidence", 0.0)
        if match.get("email_id") is None:
            return Decision(
                "reject_match",
                f"no sent email could be matched to this reply (method={match.get('method')})",
                data={"confidence": confidence},
            )
        if confidence >= MATCH_CONFIDENCE_AUTO:
            return Decision(
                "auto_learn",
                f"reply matched via {match.get('method')} with high confidence ({confidence:.2f})",
                data={"confidence": confidence},
            )
        if confidence >= MATCH_CONFIDENCE_REVIEW:
            return Decision(
                "require_human_review",
                f"reply matched via {match.get('method')} but confidence is only medium "
                f"({confidence:.2f}); needs human confirmation before learning",
                data={"confidence": confidence},
            )
        return Decision(
            "reject_match",
            f"match confidence too low to trust ({confidence:.2f})",
            data={"confidence": confidence},
        )

    def decide_on_reply_analysis(self, analysis: dict) -> Decision:
        """Gate learning on how confident the reply's intent/outcome
        classification is, independent of the matching confidence above."""
        confidence = analysis.get("confidence", 0.0)
        if confidence >= ANALYSIS_CONFIDENCE_AUTO:
            return Decision(
                "trust_analysis",
                f"reply analysis confidence {confidence:.2f} meets threshold "
                f"({ANALYSIS_CONFIDENCE_AUTO})",
                data={"confidence": confidence},
            )
        return Decision(
            "require_human_review",
            f"reply analysis confidence {confidence:.2f} below threshold "
            f"({ANALYSIS_CONFIDENCE_AUTO}); intent is ambiguous",
            data={"confidence": confidence},
        )

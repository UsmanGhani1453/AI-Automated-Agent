"""
Experience: the unit of learning. Every completed email interaction becomes
one of these before the learning engine touches it.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Experience:
    lead: Dict[str, Any]
    strategy: str
    components: Dict[str, Any]         # {"greeting": "...", "cta": "...", ...} text used
    generated_email: str
    analyzer_report: Dict[str, Any]
    decision: Dict[str, Any]           # what the decision engine chose and why
    user_action: str = "pending"       # approve, edit, reject
    user_edited_email: Optional[str] = None
    rating: Optional[int] = None       # 1-5
    replied: bool = False
    comment: str = ""
    outcome: str = "pending"           # sent, skipped, failed, pending

    def to_dict(self):
        return {
            "lead": self.lead,
            "strategy": self.strategy,
            "components": self.components,
            "generated_email": self.generated_email,
            "analyzer_report": self.analyzer_report,
            "decision": self.decision,
            "user_action": self.user_action,
            "user_edited_email": self.user_edited_email,
            "rating": self.rating,
            "replied": self.replied,
            "comment": self.comment,
            "outcome": self.outcome,
        }

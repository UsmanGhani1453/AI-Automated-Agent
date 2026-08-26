from app.tools.base import Tool
from app.database.repository import LeadRepository, SuppressionRepository


class DatabaseTool(Tool):
    name = "database"

    def execute(self, action, **kwargs):
        if action == "find_or_create_lead":
            return LeadRepository.find_or_create(kwargs["lead"])
        if action == "is_suppressed":
            return {"suppressed": SuppressionRepository.is_suppressed(kwargs["email"])}
        if action == "recently_contacted":
            return {"recent": LeadRepository.recently_contacted(kwargs["lead_id"])}
        if action == "mark_contacted":
            LeadRepository.mark_contacted(kwargs["lead_id"])
            return {"ok": True}
        raise ValueError(f"Unknown database action: {action}")

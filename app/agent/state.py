"""
AgentState: a persistent snapshot of what the agent is doing right now,
logged to agent_state on every transition so the run history is auditable.
"""
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional
from app.database.database import get_conn, now, dumps


@dataclass
class AgentState:
    goal: Optional[str] = None
    current_task: Optional[str] = None
    current_lead_id: Optional[int] = None
    memory_context: Optional[Dict[str, Any]] = None
    selected_strategy: Optional[str] = None
    quality_score: Optional[float] = None
    action: Optional[str] = None
    result: Optional[str] = None

    def log(self, agent_id=None):
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO agent_state
                   (agent_id, goal, current_task, current_lead_id, memory_context,
                    selected_strategy, quality_score, action, result, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (agent_id, self.goal, self.current_task, self.current_lead_id,
                 dumps(self.memory_context), self.selected_strategy, self.quality_score,
                 self.action, self.result, now()),
            )

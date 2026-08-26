"""
Planner: builds the fixed step sequence for "contact a new qualified lead"
and supports dynamic replanning when a step fails (skip vs abort vs retry).
Lightweight on purpose — a fixed template plan is enough at this scope;
the interesting adaptivity lives in the decision engine and learning engine,
not in plan search.
"""
from app.database.database import get_conn, now, dumps


DEFAULT_PLAN = [
    "validate_lead",
    "check_suppression",
    "check_contact_history",
    "retrieve_memory",
    "select_strategy",
    "generate_email",
    "analyze_email",
    "request_approval",
    "send_email",
    "record_result",
    "learn",
]


class Planner:
    def build_plan(self, goal: str, task_id=None):
        steps = list(DEFAULT_PLAN)
        if task_id:
            with get_conn() as conn:
                conn.execute(
                    "INSERT INTO plans (task_id, steps_json, current_step, created_at) VALUES (?, ?, 0, ?)",
                    (task_id, dumps(steps), now()),
                )
        return steps

    def replan_after_failure(self, remaining_steps, failed_step, error):
        """
        On failure: drop the failed step and continue if it's non-critical
        (e.g. analyze_email failing shouldn't stop the whole lead), otherwise
        abort the remaining plan for this lead and let the caller move to
        the next one.
        """
        non_critical = {"analyze_email", "record_result"}
        if failed_step in non_critical:
            return [s for s in remaining_steps if s != failed_step], "skipped_non_critical"
        return [], "aborted_remaining_plan"

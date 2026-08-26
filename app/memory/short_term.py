"""
Short-term memory: an in-process, per-run scratchpad for the current task.
Not persisted to disk on purpose — it represents "what the agent is thinking
about right now", distinct from long-term/episodic memory which IS persisted.
"""


class ShortTermMemory:
    def __init__(self):
        self.reset()

    def reset(self):
        self.current_lead = None
        self.current_goal = None
        self.current_action = None
        self.current_plan = None
        self.current_email = None
        self.current_evaluation = None
        self.scratch = {}

    def set(self, key, value):
        if hasattr(self, key):
            setattr(self, key, value)
        else:
            self.scratch[key] = value

    def get(self, key, default=None):
        if hasattr(self, key):
            return getattr(self, key)
        return self.scratch.get(key, default)

    def snapshot(self):
        return {
            "current_lead": self.current_lead,
            "current_goal": self.current_goal,
            "current_action": self.current_action,
            "current_plan": self.current_plan,
            "current_email": self.current_email,
            "current_evaluation": self.current_evaluation,
            "scratch": self.scratch,
        }

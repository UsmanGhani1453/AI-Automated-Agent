"""
Tool system: every capability the agent can invoke (scraping, sending email,
querying the DB, scheduling) is a Tool. The agent's Executor decides *when*
to call a tool; the ToolRegistry is just a lookup table — there is no
external orchestration framework here.
"""
import time
from app.database.repository import ToolCallRepository


class Tool:
    name = "tool"

    def execute(self, **parameters):
        raise NotImplementedError


class ToolRegistry:
    def __init__(self):
        self._tools = {}

    def register(self, tool: Tool):
        self._tools[tool.name] = tool

    def get(self, name):
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' is not registered.")
        return self._tools[name]

    def call(self, name, **parameters):
        tool = self.get(name)
        start = time.time()
        status = "success"
        result = None
        try:
            result = tool.execute(**parameters)
            return result
        except Exception as e:
            status = "failed"
            result = {"error": str(e)}
            raise
        finally:
            duration_ms = (time.time() - start) * 1000
            ToolCallRepository.log(name, parameters, result, status, duration_ms)

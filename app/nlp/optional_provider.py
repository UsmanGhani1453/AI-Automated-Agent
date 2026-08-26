"""
LocalNLPProvider: an OPTIONAL implementation of NLPProvider that calls a
locally-running Ollama model to generate a fresh candidate component (e.g. a
new "opening" line) that the Composer can then score and adopt if it performs
well. This is a tool the agent may use, not the agent's brain.

The rest of the system runs fine with self.provider = None.
"""
import requests
from app.nlp.base import NLPProvider


class LocalNLPProvider(NLPProvider):
    def __init__(self, model="gemma2:2b", host="http://localhost:11434"):
        self.model = model
        self.host = host

    def is_available(self) -> bool:
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=2)
            return r.status_code == 200
        except requests.RequestException:
            return False

    def generate(self, context: dict) -> str:
        prompt = context.get("prompt", "")
        resp = requests.post(
            f"{self.host}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()

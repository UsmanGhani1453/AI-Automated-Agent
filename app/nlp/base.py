"""
NLPProvider: the interface for an OPTIONAL language-generation component.

The agent never calls a specific model directly — it depends only on this
interface. Swap LocalNLPProvider for a rule-based one, a locally-run small
transformer, a classifier, or a model you train yourself later; nothing in
app/agent, app/memory, app/learning, or app/email/generator.py needs to change.

If no provider is configured, the agent still works: Composer builds emails
from scored components only, no generation call is required.
"""
from abc import ABC, abstractmethod


class NLPProvider(ABC):
    @abstractmethod
    def generate(self, context: dict) -> str:
        """Given a context dict (lead info, strategy, examples), return generated text.
        Implementations should raise on failure, not return silently-empty strings,
        so the caller can fall back to template-only composition."""
        raise NotImplementedError

    def is_available(self) -> bool:
        """Providers should override this with a cheap health check
        (e.g. can we reach the local Ollama server?)."""
        return True

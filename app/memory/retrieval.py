"""
Retrieval: the single entry point the agent core calls to pull relevant
memory before making a decision. Combines episodic recall + semantic
statements + learned pattern scores into one context bundle.

No embeddings/vector DB — retrieval is by lead category + location bucket
(TF-IDF-lite tag matching), which is enough at this data scale and keeps
everything explainable ("retrieved because these 3 tags matched").
"""
from app.memory.episodic import EpisodicMemory
from app.memory.semantic import SemanticMemory
from app.database.repository import PatternRepository


class MemoryRetrieval:
    def __init__(self):
        self.episodic = EpisodicMemory()
        self.semantic = SemanticMemory()

    def _tags_for_lead(self, lead):
        tags = []
        if lead.get("category"):
            tags.append(f"category:{lead['category']}")
        if lead.get("location"):
            # bucket by state/region token (last comma-separated part, or whole string)
            loc = lead["location"].split(",")[-1].strip().lower().replace(" ", "_")
            if loc:
                tags.append(f"location:{loc}")
        fleet = lead.get("fleet_size")
        if fleet:
            try:
                fleet_n = int(str(fleet).split()[0])
                bucket = "fleet:1-3" if fleet_n <= 3 else "fleet:4-10" if fleet_n <= 10 else "fleet:10+"
                tags.append(bucket)
            except (ValueError, IndexError):
                pass
        return tags

    def retrieve_context(self, lead, top_strategies=3):
        tags = self._tags_for_lead(lead)
        similar_episodes = self.episodic.find_similar(tags, limit=5)
        semantic_statements = self.semantic.derive_statements()
        strategy_scores = PatternRepository.all_for_prefix("strategy:")[:top_strategies]

        return {
            "tags": tags,
            "similar_episodes": similar_episodes,
            "semantic_statements": semantic_statements,
            "top_strategies": strategy_scores,
        }

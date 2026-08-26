"""
Episodic memory: complete "episodes" — Lead -> Email -> Evaluation -> User
decision -> Sent -> Result -> Feedback — stored as a single retrievable unit.
Distinct from semantic memory, which stores distilled *rules* extracted
across many episodes.
"""
from app.database.database import get_conn, now, dumps, loads, rows_to_dicts


class EpisodicMemory:
    def store_episode(self, lead, email, evaluation, decision, outcome, feedback, tags=None):
        content = {
            "lead": lead,
            "email": email,
            "evaluation": evaluation,
            "decision": decision,
            "outcome": outcome,
            "feedback": feedback,
        }
        # Importance weights episodes that led to a strong signal (reply, low/high rating)
        # higher, so retrieval prefers the most informative past cases.
        importance = 0.5
        if feedback:
            rating = feedback.get("rating")
            if rating is not None:
                importance = 0.9 if rating >= 4 or rating <= 2 else 0.5
            if feedback.get("replied"):
                importance = 1.0

        with get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO memories (memory_type, content_json, tags, importance, created_at)
                   VALUES ('episodic', ?, ?, ?, ?)""",
                (dumps(content), ",".join(tags or []), importance, now()),
            )
            return cur.lastrowid

    def find_similar(self, tags, limit=5):
        """Very lightweight retrieval: tag overlap + importance, no vector DB needed."""
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM memories WHERE memory_type='episodic' ORDER BY id DESC LIMIT 200"
            ).fetchall()
        candidates = rows_to_dicts(rows)
        target = set(tags or [])

        def overlap_score(row):
            row_tags = set((row["tags"] or "").split(",")) if row["tags"] else set()
            overlap = len(target & row_tags)
            return overlap * 2 + row["importance"]

        candidates.sort(key=overlap_score, reverse=True)
        top = candidates[:limit]
        for c in top:
            c["content"] = loads(c.pop("content_json"), {})
        return top

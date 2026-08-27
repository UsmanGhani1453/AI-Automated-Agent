"""Persistent inbox conversation memory for Phase 1."""
from app.database.repository import InboxMessageRepository, ConversationProfileRepository
from app.email.understanding import EmailUnderstanding

class ConversationMemory:
    def __init__(self, max_messages=10):
        self.max_messages = max_messages
        self.understanding = EmailUnderstanding()

    def ingest(self, message):
        thread_key = self.understanding.build_thread_key(message)
        enriched = {**message, "thread_key": thread_key}
        analysis = self.understanding.analyze(enriched)
        stored = InboxMessageRepository.upsert(enriched, analysis)
        messages = InboxMessageRepository.by_thread(thread_key, limit=self.max_messages)
        profile = {
            "thread_key": thread_key,
            "participant": {"name": message.get("from_name", ""), "email": message.get("from_email", "")},
            "subject": analysis["subject"],
            "message_count": len(messages),
            "prior_message_count": max(0, len(messages) - 1),
            "recent_messages": [
                {"from": m.get("from_email", ""), "subject": m.get("subject", ""), "body": (m.get("body") or "")[:1200], "date": m.get("sent_at", "")}
                for m in messages[-5:]
            ],
        }
        ConversationProfileRepository.upsert(
            thread_key, message.get("from_email", ""), message.get("from_name", ""),
            analysis["subject"], len(messages), profile,
        )
        return {"thread_key": thread_key, "analysis": analysis, "message": stored, "messages": messages, "profile": profile}

    def context_for(self, thread_key):
        return {
            "thread_key": thread_key,
            "messages": InboxMessageRepository.by_thread(thread_key, limit=self.max_messages),
            "profile": ConversationProfileRepository.get(thread_key),
        }

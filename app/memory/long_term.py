"""
Long-term memory: durable facts about leads, emails, feedback, decisions.
This is a read/write facade over the repository layer — it exists so the
agent core talks to "memory" as a concept, not to SQL tables directly.
"""
from app.database.repository import (
    LeadRepository, EmailRepository, FeedbackRepository, ExperienceRepository,
)


class LongTermMemory:
    def record_lead(self, lead_data):
        return LeadRepository.find_or_create(lead_data)

    def get_lead_history(self, lead_id, limit=5):
        return EmailRepository.recent_for_lead(lead_id, limit=limit)

    def record_feedback(self, email_id, rating, action, comment="", replied=False):
        return FeedbackRepository.create(email_id, rating, action, comment, replied)

    def record_experience(self, lead_id, email_id, context, decision, evaluation, outcome, feedback):
        return ExperienceRepository.create(
            lead_id, email_id, context, decision, evaluation, outcome, feedback
        )

    def recent_experiences(self, limit=50):
        return ExperienceRepository.recent(limit=limit)

"""
Learning engine: the orchestrator for online learning.

Given a completed Experience, it:
  1. Persists it as an experience record (long-term memory).
  2. Stores it as an episode (episodic memory) for future retrieval.
  3. Updates strategy + component pattern scores (pattern scorer).
  4. If the user edited the email, extracts structural preferences (preference learner).
  5. Leaves an explainable trail so `explain_last_decision` can answer
     "why did you choose this email style?" with real numbers.

This is NOT "retrain a neural net after every email" — it's classic online/
incremental learning over explicit, auditable statistics, which is exactly
what was asked for and what's tractable on this hardware.
"""
from app.learning.pattern_scorer import PatternScorer
from app.learning.preference_learner import PreferenceLearner
from app.memory.episodic import EpisodicMemory
from app.memory.long_term import LongTermMemory
from app.database.repository import ComponentRepository, PatternRepository


class LearningEngine:
    def __init__(self):
        self.scorer = PatternScorer()
        self.preference_learner = PreferenceLearner()
        self.episodic = EpisodicMemory()
        self.long_term = LongTermMemory()

    def learn(self, experience, email_id=None, component_ids=None):
        """
        experience: learning.experience.Experience
        component_ids: dict of {component_type: component_row_id} used in the email,
                        so per-component scores can be updated too.
        """
        rating = experience.rating
        replied = experience.replied

        # 1. Update strategy-level score
        strategy_pattern = None
        if rating is not None or replied:
            strategy_pattern = self.scorer.score_strategy(experience.strategy, rating=rating, replied=replied)

        # 2. Update component-level scores
        if component_ids and (rating is not None or replied):
            for comp_type, comp_id in component_ids.items():
                self.scorer.score_component(comp_id, rating or 3, replied=replied)
                # Mirror into learned_patterns too, keyed by type+text, for semantic-memory rendering
                comp_row = ComponentRepository.top_for_type(comp_type, limit=50)
                match = next((c for c in comp_row if c["id"] == comp_id), None)
                if match:
                    key = f"component:{comp_type}:{match['text'][:30]}"
                    PatternRepository.update_score(key, rating=rating, replied=replied)

        # 3. Extract structural preferences from user edits
        findings = []
        if experience.user_edited_email:
            findings = self.preference_learner.learn_from_edit(
                experience.generated_email, experience.user_edited_email
            )

        # 4. Persist as experience + episode
        self.long_term.record_experience(
            lead_id=experience.lead.get("id"),
            email_id=email_id,
            context={"lead": experience.lead, "components": experience.components},
            decision=experience.decision,
            evaluation=experience.analyzer_report,
            outcome=experience.outcome,
            feedback={
                "rating": rating, "replied": replied,
                "comment": experience.comment, "user_action": experience.user_action,
                "preference_findings": findings,
            },
        )
        self.episodic.store_episode(
            lead=experience.lead,
            email=experience.generated_email,
            evaluation=experience.analyzer_report,
            decision=experience.decision,
            outcome=experience.outcome,
            feedback={"rating": rating, "replied": replied, "comment": experience.comment},
            tags=self._tags_for(experience.lead),
        )

        return {
            "strategy_pattern": strategy_pattern,
            "preference_findings": findings,
        }

    def _tags_for(self, lead):
        tags = []
        if lead.get("category"):
            tags.append(f"category:{lead['category']}")
        if lead.get("location"):
            tags.append(f"location:{lead['location'].split(',')[-1].strip().lower().replace(' ', '_')}")
        return tags

    def explain_strategy_choice(self, strategy):
        return self.scorer.explain(f"strategy:{strategy}")

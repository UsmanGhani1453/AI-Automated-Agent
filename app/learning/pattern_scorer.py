"""
Pattern scorer: turns feedback into updated, explainable scores for
- strategies (SHORT_DIRECT, LOCATION_PERSONALIZED, ...)
- individual email components (a specific greeting/cta/opening text)

Formula (deliberately simple and explainable, no black box):

    score = (positive_count + REPLY_WEIGHT * reply_count + SMOOTHING * 0.5)
            / (positive_count + negative_count + REPLY_WEIGHT * reply_count + SMOOTHING)

This is Laplace/Bayesian smoothing: with zero samples the score is exactly
0.5 (neutral prior), and it needs several consistent samples before moving
far from neutral — which avoids one lucky/unlucky email swinging behavior.
A reply counts as REPLY_WEIGHT positive samples because it's a much stronger
signal of email quality than a subjective star rating.
"""
from app.database.repository import PatternRepository, ComponentRepository, PreferenceRepository

REPLY_WEIGHT = 2
SMOOTHING = 2.0


class PatternScorer:
    def score_strategy(self, strategy, rating=None, replied=False):
        return PatternRepository.update_score(f"strategy:{strategy}", rating=rating, replied=replied)

    def score_component(self, component_id, rating, replied=False):
        ComponentRepository.apply_feedback(component_id, rating, replied=replied)

    def explain(self, pattern_key):
        pat = PatternRepository.get(pattern_key)
        if not pat:
            return f"No data yet for '{pattern_key}'."
        return (
            f"{pattern_key}: score={pat['score']:.2f} "
            f"from {pat['sample_count']} samples "
            f"({pat['positive_feedback']} positive, {pat['negative_feedback']} negative, "
            f"{pat['reply_count']} replies)."
        )

    def record_preference_signal(self, key, description, positive):
        """Nudge a preference's confidence up or down based on one more piece of evidence."""
        delta = 0.08 if positive else -0.05
        PreferenceRepository.upsert(key, description, delta)

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

    # Preferences that represent opposite interpretations of the same signal.
    # When evidence strengthens one side, the competing side is weakened.
    PREFERENCE_OPPOSITES = {
        "prefers_shorter_emails": (
            "prefers_detailed_emails",
            "User prefers more detailed emails than the AI draft.",
        ),
        "prefers_detailed_emails": (
            "prefers_shorter_emails",
            "User prefers shorter emails than the AI draft.",
        ),
        "prefers_casual_greeting": (
            "prefers_formal_greeting",
            "User prefers formal greetings over casual greetings.",
        ),
        "prefers_formal_greeting": (
            "prefers_casual_greeting",
            "User prefers casual greetings over formal greetings.",
        ),
        "prefers_casual_signoff": (
            "prefers_formal_signoff",
            "User prefers a more formal sign-off.",
        ),
        "prefers_formal_signoff": (
            "prefers_casual_signoff",
            "User prefers a more casual sign-off.",
        ),
        "allows_exclamation": (
            "prefers_no_exclamation",
            "User prefers no exclamation marks.",
        ),
        "prefers_no_exclamation": (
            "allows_exclamation",
            "User sometimes allows or adds exclamation marks.",
        ),
    }

    def record_preference_signal(self, key, description, positive):
        """Record preference evidence and weaken contradictory evidence.

        Positive evidence raises the observed preference. If that preference
        has a known opposite, the opposite confidence is reduced by the same
        signal. This prevents contradictory preferences from accumulating
        independently over time.
        """
        delta = 0.08 if positive else -0.05
        PreferenceRepository.upsert(key, description, delta)

        if positive and key in self.PREFERENCE_OPPOSITES:
            opposite_key, opposite_description = self.PREFERENCE_OPPOSITES[key]
            PreferenceRepository.upsert(
                opposite_key,
                opposite_description,
                -0.08,
            )

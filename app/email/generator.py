"""
EmailGenerator: the multi-stage pipeline described in the spec.

Lead Data -> Context Builder -> Memory Retrieval -> Strategy Selection ->
Email Structure -> Content Generation -> Email Analyzer -> Quality Score ->
Accept/Regenerate

Strategy selection and candidate ranking are driven by learned pattern
scores (via PatternRepository / ComponentRepository), not by hardcoded
rules or an LLM call. An NLPProvider *may* be plugged in later purely to
generate additional candidate component text, but the pipeline itself
does not require one.
"""
from app.email.composer import Composer
from app.email.analyzer import EmailAnalyzer
from app.database.repository import PatternRepository, PreferenceRepository

STRATEGIES = ["SHORT_DIRECT", "PROFESSIONAL_INTRO", "LOCATION_PERSONALIZED", "VALUE_FIRST"]
QUALITY_THRESHOLD = 0.55
MAX_ATTEMPTS = 3


class EmailGenerator:
    def __init__(self, nlp_provider=None):
        self.composer = Composer(nlp_provider=nlp_provider)
        self.analyzer = EmailAnalyzer()
        self.nlp_provider = nlp_provider  # optional, replaceable, never required

    def select_strategy(self):
        """Select a strategy using learned performance plus user preferences.

        Strategy performance remains the primary signal. User preferences provide
        a confidence-weighted bonus only when the preference has a clear
        relationship to a strategy. This prevents weak preference evidence from
        overpowering actual strategy outcomes.
        """
        scored = []

        preferences = {
            p["preference_key"]: p["confidence"]
            for p in PreferenceRepository.all()
        }

        for strategy in STRATEGIES:
            pat = PatternRepository.get(f"strategy:{strategy}")
            base_score = pat["score"] if pat else 0.5
            samples = pat["sample_count"] if pat else 0

            preference_bonus = 0.0

            shorter_conf = preferences.get("prefers_shorter_emails", 0.0)
            detailed_conf = preferences.get("prefers_detailed_emails", 0.0)

            if strategy == "SHORT_DIRECT":
                preference_bonus += 0.20 * shorter_conf

            elif strategy in ("PROFESSIONAL_INTRO", "VALUE_FIRST"):
                preference_bonus += 0.20 * detailed_conf

            final_score = base_score + preference_bonus
            scored.append((strategy, final_score, samples))

        under_explored = [s for s, _, samples in scored if samples < 3]
        if under_explored:
            import random
            return random.choice(under_explored)

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[0][0]

    def generate(self, lead, sender, retrieved_context=None, forced_strategy=None):
        strategy = forced_strategy or self.select_strategy()
        attempts = []

        for attempt in range(1, MAX_ATTEMPTS + 1):
            candidates = self.composer.generate_candidates(lead,sender,n_candidates=3,strategy=strategy,retrieved_context=retrieved_context,)
            scored_candidates = []
            for c in candidates:
                report = self.analyzer.analyze(c["body"], lead)
                scored_candidates.append({**c, "analyzer_report": report})

            scored_candidates.sort(key=lambda c: c["analyzer_report"]["quality_score"], reverse=True)
            best = scored_candidates[0]
            attempts.append({
                "attempt": attempt,
                "quality_score": best["analyzer_report"]["quality_score"],
            })

            if best["analyzer_report"]["quality_score"] >= QUALITY_THRESHOLD:
                break

        return {
            "strategy": strategy,
            "body": best["body"],
            "components": {k: v["text"] for k, v in best["components"].items()},
            "component_ids": best["component_ids"],
            "analyzer_report": best["analyzer_report"],
            "attempts": attempts,
            "regenerated": len(attempts) > 1,
        }

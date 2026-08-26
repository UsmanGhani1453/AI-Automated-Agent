"""
Integration test corresponding directly to the project's stated success
criterion (spec section 30): after enough positive feedback, a strategy's
score should measurably increase, and strategy selection should favor it.
"""
from app.email.generator import EmailGenerator
from app.learning.pattern_scorer import PatternScorer
from app.database.repository import PatternRepository


def test_learning_shifts_strategy_selection():
    scorer = PatternScorer()

    # Give every strategy a few baseline samples first so none are "under-explored"
    # (select_strategy forces exploration for strategies with <3 samples).
    from app.email.generator import STRATEGIES
    for s in STRATEGIES:
        for _ in range(3):
            scorer.score_strategy(s, rating=3)

    # Now push CTA-style strategy's score up sharply with consistent positive feedback + replies
    for _ in range(20):
        scorer.score_strategy("VALUE_FIRST", rating=5, replied=True)

    before = PatternRepository.get("strategy:VALUE_FIRST")["score"]
    assert before > 0.8  # strong, consistent positive signal should dominate

    generator = EmailGenerator()
    # With no under-explored strategies left, select_strategy should now prefer
    # the highest-scoring one deterministically.
    chosen = generator.select_strategy()
    assert chosen == "VALUE_FIRST"


def test_quality_score_measurable_before_and_after():
    """Mirrors the spec's example: 'CTA strategy score = 0.52 -> 0.81 after 20 positive examples.'"""
    scorer = PatternScorer()
    PatternRepository.get_or_create("strategy:DEMO_STRATEGY")
    baseline = PatternRepository.get("strategy:DEMO_STRATEGY")["score"]
    assert baseline == 0.5

    for _ in range(20):
        scorer.score_strategy("DEMO_STRATEGY", rating=5)

    after = PatternRepository.get("strategy:DEMO_STRATEGY")["score"]
    assert after > baseline
    assert after > 0.7

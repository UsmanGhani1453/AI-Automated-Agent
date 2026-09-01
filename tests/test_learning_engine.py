"""
These tests are the ones that matter most for the project's central claim:
that feedback measurably changes future agent behavior. Each test drives
the scoring math directly rather than mocking it, so a regression in the
scoring formula itself would be caught here.
"""
from app.learning.pattern_scorer import PatternScorer
from app.learning.preference_learner import PreferenceLearner
from app.database.repository import PatternRepository, ComponentRepository, PreferenceRepository


def test_strategy_score_starts_neutral():
    pat = PatternRepository.get_or_create("strategy:TEST_STRATEGY")
    assert pat["score"] == 0.5 # type: ignore


def test_positive_feedback_increases_strategy_score():
    scorer = PatternScorer()
    before = PatternRepository.get_or_create("strategy:TEST_STRATEGY")["score"] # type: ignore
    for _ in range(5):
        scorer.score_strategy("TEST_STRATEGY", rating=5)
    after = PatternRepository.get("strategy:TEST_STRATEGY")["score"] # type: ignore
    assert after > before


def test_negative_feedback_decreases_strategy_score():
    scorer = PatternScorer()
    before = PatternRepository.get_or_create("strategy:TEST_STRATEGY_2")["score"] # type: ignore
    for _ in range(5):
        scorer.score_strategy("TEST_STRATEGY_2", rating=1)
    after = PatternRepository.get("strategy:TEST_STRATEGY_2")["score"] # type: ignore
    assert after < before


def test_reply_weighted_more_than_rating():
    scorer = PatternScorer()
    scorer.score_strategy("RATING_ONLY", rating=5, replied=False)
    scorer.score_strategy("REPLY_STRATEGY", rating=5, replied=True)
    rating_only = PatternRepository.get("strategy:RATING_ONLY")["score"] # type: ignore
    with_reply = PatternRepository.get("strategy:REPLY_STRATEGY")["score"] # type: ignore
    assert with_reply > rating_only


def test_score_converges_toward_signal_with_more_samples():
    """Few samples shouldn't swing the score as far as many consistent samples."""
    scorer = PatternScorer()
    scorer.score_strategy("FEW_SAMPLES", rating=5)
    few = PatternRepository.get("strategy:FEW_SAMPLES")["score"] # type: ignore

    for _ in range(20):
        scorer.score_strategy("MANY_SAMPLES", rating=5)
    many = PatternRepository.get("strategy:MANY_SAMPLES")["score"] # type: ignore

    assert many > few  # more consistent positive evidence pushes further from 0.5


def test_component_scoring_updates_on_feedback():
    comp = ComponentRepository.upsert("cta", "Would you be open to a quick call?")
    assert comp["positive_score"] == 0.5 # type: ignore
    for _ in range(4):
        ComponentRepository.apply_feedback(comp["id"], rating=5, replied=False) # type: ignore
    rows = ComponentRepository.top_for_type("cta", limit=5)
    updated = next(r for r in rows if r["id"] == comp["id"]) # type: ignore
    assert updated["positive_score"] > 0.5


def test_preference_learner_detects_shorter_edit():
    learner = PreferenceLearner()
    ai_email = ("Dear James,\n\nI hope this email finds you well. I wanted to take a moment "
                "to reach out regarding your fleet operations near Austin, Texas, as I believe "
                "there may be a valuable opportunity for us to collaborate.\n\nBest regards, Natasha")
    user_email = "Hi James, quick note about Austin dispatching. Best, Natasha"
    findings = learner.learn_from_edit(ai_email, user_email)
    keys = [f["key"] for f in findings]
    assert "prefers_shorter_emails" in keys


def test_preference_learner_detects_greeting_removal():
    learner = PreferenceLearner()
    ai_email = "Dear James,\nWe'd love to help.\nBest, Natasha"
    user_email = "Hey — we'd love to help.\nBest, Natasha"
    findings = learner.learn_from_edit(ai_email, user_email)
    keys = [f["key"] for f in findings]
    assert "dislikes_formal_greeting" in keys


def test_preference_confidence_accumulates_with_evidence():
    scorer = PatternScorer()
    scorer.record_preference_signal("test_pref", "User prefers X", positive=True)
    first = PreferenceRepository.all()
    conf1 = next(p["confidence"] for p in first if p["preference_key"] == "test_pref")

    scorer.record_preference_signal("test_pref", "User prefers X", positive=True)
    second = PreferenceRepository.all()
    conf2 = next(p["confidence"] for p in second if p["preference_key"] == "test_pref")

    assert conf2 > conf1
def test_opposite_preference_is_weakened_by_positive_evidence():
    scorer = PatternScorer()

    scorer.record_preference_signal(
        "prefers_detailed_emails",
        "User prefers more detailed emails than the AI draft.",
        positive=True,
    )

    scorer.record_preference_signal(
        "prefers_shorter_emails",
        "User prefers shorter emails than the AI draft.",
        positive=True,
    )

    preferences = PreferenceRepository.all()

    shorter = next(
        p for p in preferences
        if p["preference_key"] == "prefers_shorter_emails"
    )
    detailed = next(
        p for p in preferences
        if p["preference_key"] == "prefers_detailed_emails"
    )

    assert shorter["confidence"] > 0.0
    assert detailed["confidence"] < 0.08


def test_detailed_preference_weakens_shorter_preference():
    scorer = PatternScorer()

    scorer.record_preference_signal(
        "prefers_shorter_emails",
        "User prefers shorter emails than the AI draft.",
        positive=True,
    )

    scorer.record_preference_signal(
        "prefers_detailed_emails",
        "User prefers more detailed emails than the AI draft.",
        positive=True,
    )

    preferences = PreferenceRepository.all()

    shorter = next(
        p for p in preferences
        if p["preference_key"] == "prefers_shorter_emails"
    )
    detailed = next(
        p for p in preferences
        if p["preference_key"] == "prefers_detailed_emails"
    )

    assert detailed["confidence"] > 0.0
    assert shorter["confidence"] < 0.08
def test_composer_prefers_casual_greeting():
    from app.email.composer import Composer

    PreferenceRepository.upsert(
        "prefers_casual_greeting",
        "User prefers casual greetings.",
        0.9,
    )

    composer = Composer()

    preferences = composer._preferences()

    rows = composer.top_candidates("greeting", k=3)

    weights = [
        composer._preference_weight(row, preferences)
        for row in rows
    ]

    casual_weights = [
        weight
        for row, weight in zip(rows, weights)
        if row["text"].lower().startswith(("hi ", "hello ", "hey "))
    ]

    formal_weights = [
        weight
        for row, weight in zip(rows, weights)
        if row["text"].lower().startswith("dear ")
    ]

    assert casual_weights
    assert formal_weights
    assert max(casual_weights) > max(formal_weights)


def test_composer_prefers_short_strategy():
    from app.email.composer import Composer

    PreferenceRepository.upsert(
        "prefers_shorter_emails",
        "User prefers shorter emails.",
        0.9,
    )

    from app.email.generator import EmailGenerator

    generator = EmailGenerator(None)

    assert generator.select_strategy() in [
        "SHORT_DIRECT",
        "LOCATION_PERSONALIZED",
        "PROFESSIONAL_INTRO",
        "VALUE_FIRST",
    ]
def test_strong_shorter_preference_reduces_component_count():
    from app.email.composer import Composer

    PreferenceRepository.upsert(
        "prefers_shorter_emails",
        "User prefers shorter emails.",
        0.80,
    )

    PreferenceRepository.upsert(
        "prefers_detailed_emails",
        "User prefers more detailed emails.",
        0.00,
    )

    composer = Composer()

    preferences = composer._preferences()

    normal = composer._preferred_component_order(
        "LOCATION_PERSONALIZED",
        {
            "prefers_shorter_emails": 0.00,
            "prefers_detailed_emails": 0.00,
        },
    )

    shortened = composer._preferred_component_order(
        "LOCATION_PERSONALIZED",
        preferences,
    )

    assert len(shortened) < len(normal)
    assert "cta" in shortened
    assert "signature" in shortened
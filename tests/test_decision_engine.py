from app.agent.decision_engine import DecisionEngine
from app.database.repository import SuppressionRepository, LeadRepository


def make_lead(**overrides):
    lead = {
        "email": "test@example.com", "officer": "Jane", "company": "Acme Freight",
        "fleet_size": "2", "location": "Austin, TX",
    }
    lead.update(overrides)
    return lead


def test_rejects_invalid_email():
    engine = DecisionEngine()
    decision = engine.decide_on_lead(make_lead(email="not-an-email"))
    assert decision.action == "reject_lead"
    assert "invalid" in decision.reason


def test_rejects_lead_with_no_identity():
    engine = DecisionEngine()
    decision = engine.decide_on_lead(make_lead(officer="", company=""))
    assert decision.action == "reject_lead"


def test_respects_suppression_list():
    SuppressionRepository.add("blocked@example.com", reason="unsubscribed")
    engine = DecisionEngine()
    decision = engine.decide_on_lead(make_lead(email="blocked@example.com"))
    assert decision.action == "do_not_contact"
    assert "suppression" in decision.reason


def test_skips_recently_contacted_lead():
    lead_row = LeadRepository.find_or_create(make_lead(email="recent@example.com"))
    LeadRepository.mark_contacted(lead_row["id"])

    engine = DecisionEngine()
    lead = make_lead(email="recent@example.com")
    lead["id"] = lead_row["id"]
    decision = engine.decide_on_lead(lead)
    assert decision.action == "skip"
    assert "contacted" in decision.reason


def test_valid_new_lead_proceeds():
    engine = DecisionEngine()
    decision = engine.decide_on_lead(make_lead(email="fresh@example.com"))
    assert decision.action == "proceed"


def test_regenerate_below_quality_threshold_with_attempts_remaining():
    engine = DecisionEngine()
    report = {"quality_score": 0.3, "placeholder_found": False}
    decision = engine.decide_on_email(report, attempt=1, max_attempts=3)
    assert decision.action == "regenerate"


def test_requires_human_review_after_max_attempts():
    engine = DecisionEngine()
    report = {"quality_score": 0.3, "placeholder_found": False}
    decision = engine.decide_on_email(report, attempt=3, max_attempts=3)
    assert decision.action == "require_human_review"


def test_accepts_good_quality_email():
    engine = DecisionEngine()
    report = {"quality_score": 0.8, "placeholder_found": False}
    decision = engine.decide_on_email(report, attempt=1, max_attempts=3)
    assert decision.action == "request_approval"


def test_placeholder_forces_regeneration_even_with_high_score():
    engine = DecisionEngine()
    report = {"quality_score": 0.9, "placeholder_found": True}
    decision = engine.decide_on_email(report, attempt=1, max_attempts=3)
    assert decision.action == "regenerate"


def test_approval_decision():
    engine = DecisionEngine()
    assert engine.decide_after_approval(True).action == "send"
    assert engine.decide_after_approval(False).action == "hold"

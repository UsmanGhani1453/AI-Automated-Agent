"""
Phase 7.5 — the most important test in this suite.

Not "do the functions execute" but: does the agent's behavior actually
change because of a real interaction outcome? This exercises the full
loop: generate -> send (dry run) -> receive reply -> analyze -> match ->
learn -> generate again, and asserts the *second* generation was
influenced by what was learned from the *first* interaction's reply.
"""
import os

from app.agent.agent import Agent
from app.database.repository import PatternRepository, ReplyRepository, LeadRepository


SENDER = {
    "sender_name": "Alex Rivera",
    "sender_title": "Dispatch Manager",
    "sender_email": "alex@example.com",
}

LEAD = {
    "officer": "Jane Doe",
    "company": "Doe Trucking",
    "fleet_size": "3",
    "location": "Dallas, TX",
    "email": "jane@doetrucking.example.com",
    "category": "owner_operator",
}


def make_agent():
    os.environ["EMAIL_DRY_RUN"] = "true"
    return Agent(sender_info=SENDER, dry_run=True)


def test_idempotency_same_reply_not_learned_twice():
    agent = make_agent()
    log = agent.run_for_lead(LEAD, auto_approve=True)
    assert log["outcome"] == "dry_run"
    email_id = log["send_result"] and None  # dry run has no email_id in send_result
    # fetch the email that was generated for this lead
    from app.database.repository import EmailRepository
    lead = LeadRepository.get_by_email(LEAD["email"])
    sent = EmailRepository.recent_for_lead(lead["id"], limit=1)[0]

    reply_message = {
        "id": "mailbox-1",
        "message_id": "<r1@reply.example.com>",
        "from_email": lead["email"],
        "to": SENDER["sender_email"],
        "subject": "Re: Freight Dispatching Services near Dallas, TX",
        "body": "This sounds great, I'm interested, let's set up a call.",
    }

    first = agent.process_reply(reply_message)
    assert first["outcome"] == "learned"
    assert ReplyRepository.is_learned("mailbox-1")

    second = agent.process_reply(reply_message)
    assert second["outcome"] == "already_learned"


def test_low_confidence_match_is_not_learned():
    agent = make_agent()
    reply_message = {
        "id": "mailbox-stranger",
        "from_email": "someone-unrelated@nowhere.example.com",
        "to": SENDER["sender_email"],
        "subject": "hi",
        "body": "not interested",
    }
    result = agent.process_reply(reply_message)
    assert result["outcome"] == "match_rejected"
    assert not ReplyRepository.is_learned("mailbox-stranger")


def test_reply_updates_strategy_pattern_score():
    agent = make_agent()
    log = agent.run_for_lead(LEAD, auto_approve=True, simulated_feedback=None)
    strategy = log["decision"] and None  # not directly exposed; read from email row
    from app.database.repository import EmailRepository
    lead = LeadRepository.get_by_email(LEAD["email"])
    sent = EmailRepository.recent_for_lead(lead["id"], limit=1)[0]
    strategy_used = sent["strategy"]

    before = PatternRepository.get(f"strategy:{strategy_used}")
    before_samples = before["sample_count"] if before else 0

    reply_message = {
        "id": "mailbox-2",
        "from_email": lead["email"],
        "to": SENDER["sender_email"],
        "subject": "Re: hello",
        "body": "Sounds great, I'm interested — let's schedule a call.",
    }
    result = agent.process_reply(reply_message)
    assert result["outcome"] == "learned"

    after = PatternRepository.get(f"strategy:{strategy_used}")
    assert after["sample_count"] == before_samples + 1
    assert after["reply_count"] >= 1


def test_end_to_end_behavior_changes_from_reply():
    """
    Create Lead -> Generate Email A -> Simulate Send -> Recipient Reply
    (positive, high confidence) -> Analyze -> Learn -> Generate Email B
    -> verify learned information influenced Email B's strategy scoring.

    We force the same strategy across many leads with a positive reply
    each time and confirm its learned score rises measurably above a
    neutral prior (0.5) and above an untouched competing strategy —
    i.e. the agent's future strategy *selection* is provably different
    after experience than it would have been before any replies.
    """
    agent = make_agent()

    forced_strategy = "SHORT_DIRECT"
    untouched_strategy = "VALUE_FIRST"

    for i in range(5):
        lead = dict(LEAD)
        lead["email"] = f"jane{i}@doetrucking.example.com"

        generated = agent.execute_generate_email(
            agent.perceive(lead), forced_strategy=forced_strategy,
        )
        from app.database.repository import EmailRepository
        lead_row = LeadRepository.get_by_email(lead["email"])
        email_id = EmailRepository.create(
            lead_id=lead_row["id"], strategy=generated["strategy"],
            components=generated["components"], body=generated["body"],
            quality_score=generated["analyzer_report"]["quality_score"],
            analyzer_report=generated["analyzer_report"],
        )
        EmailRepository.mark_sent(email_id)

        reply_message = {
            "id": f"mailbox-e2e-{i}",
            "from_email": lead["email"],
            "to": SENDER["sender_email"],
            "subject": "Re: outreach",
            "body": "This is great, I'm very interested, let's talk soon!",
        }
        result = agent.process_reply(reply_message)
        assert result["outcome"] == "learned"

    forced_score = PatternRepository.get(f"strategy:{forced_strategy}")
    untouched_score = PatternRepository.get(f"strategy:{untouched_strategy}")

    # The strategy that consistently got positive replies must now score
    # measurably higher than its 0.5 neutral prior...
    assert forced_score["score"] > 0.5
    # ...and higher than a strategy that received no signal at all.
    untouched_baseline = untouched_score["score"] if untouched_score else 0.5
    assert forced_score["score"] > untouched_baseline

    # Give every other strategy enough neutral (non-positive) samples to
    # leave the forced-exploration phase, so selection reflects the learned
    # scores rather than "under-sampled strategy get a free look" logic.
    from app.database.repository import PatternRepository as PR
    from app.learning.pattern_scorer import PatternScorer
    scorer = PatternScorer()
    for strategy in ("PROFESSIONAL_INTRO", "LOCATION_PERSONALIZED", "VALUE_FIRST"):
        for _ in range(3):
            scorer.score_strategy(strategy, rating=3, replied=False)

    # With every strategy now past the exploration threshold, selection must
    # provably favor the strategy that was reinforced by real reply outcomes.
    chosen = [agent.generator.select_strategy() for _ in range(30)]
    assert chosen.count(forced_strategy) > len(chosen) / 2

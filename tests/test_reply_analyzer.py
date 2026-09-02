from app.email.reply_analyzer import ReplyAnalyzer


def analyze(body, subject=""):
    return ReplyAnalyzer().analyze(body, subject)


def test_positive_interested_reply():
    r = analyze("This sounds great, I'm interested — tell me more!")
    assert r["intent"] == "interested"
    assert r["sentiment"] == "positive"
    assert r["outcome"] == "positive"
    assert r["interest_level"] == "high"


def test_not_interested_reply():
    r = analyze("Thanks but we're not interested, we already have a dispatcher.")
    assert r["intent"] == "not_interested"
    assert r["outcome"] == "negative"
    assert r["objection"] == "already_has_provider"


def test_meeting_request_reply():
    r = analyze("Could we schedule a quick call this week to discuss?")
    assert r["intent"] == "meeting_request"
    assert r["outcome"] == "positive"
    assert r["interest_level"] == "high"


def test_price_objection_reply():
    r = analyze("How much do you charge? Seems like it might be too expensive for us.")
    assert r["intent"] == "price_request"
    assert r["outcome"] == "needs_follow_up"
    assert r["objection"] == "price"


def test_unsubscribe_reply():
    r = analyze("Please unsubscribe me from this list.")
    assert r["intent"] == "unsubscribe"
    assert r["outcome"] == "no_opportunity"
    assert r["interest_level"] == "none"


def test_generic_question_reply():
    r = analyze("What areas do you cover?")
    assert r["intent"] in ("question", "request_information")
    assert r["question"] or r["intent"] == "request_information"


def test_neutral_reply_with_no_signal():
    r = analyze("Got it, thanks.")
    assert r["intent"] == "neutral"
    assert r["outcome"] == "unknown"


def test_unknown_reply_when_empty():
    r = analyze("")
    assert r["intent"] == "unknown"
    assert r["confidence"] == 0.0


def test_follow_up_later_reply():
    r = analyze("Not right now, but maybe check back with me next quarter.")
    assert r["intent"] == "follow_up"
    assert r["outcome"] == "needs_follow_up"


def test_all_fields_present():
    r = analyze("Sounds interesting, can you send more information?")
    for key in (
        "intent", "sentiment", "interest_level", "objection", "question",
        "requested_action", "urgency", "topic", "outcome", "confidence",
    ):
        assert key in r

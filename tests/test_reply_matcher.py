from app.database.repository import LeadRepository, EmailRepository
from app.email.reply_matcher import ReplyMatcher


def make_lead(email="lead@example.com"):
    lead_id = LeadRepository.create("Officer", "Acme Co", "3", "Lahore", email, "owner_operator")
    return LeadRepository.get(lead_id)


def make_sent_email(lead_id, message_id=None):
    email_id = EmailRepository.create(
        lead_id=lead_id, strategy="SHORT_DIRECT", components={}, body="hello",
        quality_score=0.7, analyzer_report={},
    )
    EmailRepository.mark_sent(email_id)
    if message_id:
        EmailRepository.set_outgoing_message_id(email_id, message_id)
    return email_id


def test_match_via_in_reply_to_header():
    lead = make_lead()
    email_id = make_sent_email(lead["id"], message_id="<abc123@mail.example.com>")

    match = ReplyMatcher().match({
        "sender_email": lead["email"],
        "subject": "Re: hello",
        "in_reply_to": "<abc123@mail.example.com>",
        "references": "",
    })

    assert match["email_id"] == email_id
    assert match["lead_id"] == lead["id"]
    assert match["method"] == "in_reply_to"
    assert match["confidence"] >= 0.9


def test_match_via_message_id_in_references():
    lead = make_lead()
    email_id = make_sent_email(lead["id"], message_id="<xyz789@mail.example.com>")

    match = ReplyMatcher().match({
        "sender_email": lead["email"],
        "subject": "Re: hello",
        "in_reply_to": "",
        "references": "<other@x.com> <xyz789@mail.example.com>",
    })

    assert match["email_id"] == email_id
    assert match["method"] == "references"


def test_match_via_sender_when_no_headers():
    lead = make_lead()
    email_id = make_sent_email(lead["id"])

    match = ReplyMatcher().match({
        "sender_email": lead["email"],
        "subject": "Re: hello",
        "in_reply_to": "",
        "references": "",
    })

    assert match["email_id"] == email_id
    assert match["method"] == "sender"
    assert 0.8 <= match["confidence"] < 0.95


def test_sender_matches_lead_but_nothing_sent():
    lead = make_lead()

    match = ReplyMatcher().match({
        "sender_email": lead["email"],
        "subject": "Re: hello",
        "in_reply_to": "",
        "references": "",
    })

    assert match["email_id"] is None
    assert match["lead_id"] == lead["id"]
    assert match["method"] == "sender_no_sent_email"


def test_no_match_when_nothing_lines_up():
    match = ReplyMatcher().match({
        "sender_email": "stranger@nowhere.com",
        "subject": "hi",
        "in_reply_to": "",
        "references": "",
    })

    assert match["email_id"] is None
    assert match["lead_id"] is None
    assert match["method"] == "none"
    assert match["confidence"] == 0.0


def test_ambiguous_header_does_not_false_positive():
    # A header that matches no tracked email should fall through to sender
    # matching rather than crashing or returning a spurious match.
    lead = make_lead()
    email_id = make_sent_email(lead["id"])  # no message id recorded

    match = ReplyMatcher().match({
        "sender_email": lead["email"],
        "subject": "Re: hello",
        "in_reply_to": "<unrelated@somewhere.com>",
        "references": "",
    })

    assert match["email_id"] == email_id
    assert match["method"] == "sender"

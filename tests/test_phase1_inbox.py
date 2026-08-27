from app.email.understanding import EmailUnderstanding
from app.email.reply_generator import ReplyGenerator
from app.memory.conversation import ConversationMemory
from app.database.repository import InboxMessageRepository


def sample_message(
    message_id="1",
    subject="Need the details",
    body="Could you send me the document today?",
):
    return {
        "id": message_id,
        "message_id": f"<{message_id}@example.com>",
        "from": "John Doe <john@example.com>",
        "from_name": "John Doe",
        "from_email": "john@example.com",
        "to": "me@example.com",
        "subject": subject,
        "date": "Wed, 26 Aug 2026 10:00:00 +0500",
        "body": body,
    }


def test_understanding_extracts_intent_and_urgency():
    result = EmailUnderstanding().analyze(sample_message())

    assert result["category"] == "actionable"
    assert result["intent"] == "information_request"
    assert result["urgency"] == "high"
    assert result["should_reply"] is True


def test_conversation_memory_persists_thread():
    memory = ConversationMemory()

    first = memory.ingest(
        sample_message("1")
    )

    second = memory.ingest(
        sample_message(
            "2",
            subject="Re: Need the details",
            body="Yes, please send it.",
        )
    )

    assert first["thread_key"] == second["thread_key"]
    assert second["profile"]["message_count"] == 2
    assert len(second["messages"]) == 2

    stored = InboxMessageRepository.by_thread(
        second["thread_key"],
        limit=10,
    )

    assert len(stored) == 2


def test_reply_generator_uses_context():
    memory = ConversationMemory()

    memory.ingest(sample_message("1"))

    context = memory.ingest(
        sample_message(
            "2",
            subject="Re: Need the details",
            body="Any update?",
        )
    )

    draft = ReplyGenerator(
        {
            "sender_name": "Usman",
            "sender_title": "Software Engineer",
        }
    ).draft(
        sample_message(
            "2",
            subject="Re: Need the details",
            body="Any update?",
        ),
        conversation_context=context,
    )

    assert draft["should_reply"] is True
    assert draft["conversation"]["prior_message_count"] == 1
    assert "follow up" in draft["body"].lower()


def test_meeting_request_is_understood_correctly():
    message = {
        "id": "meeting-1",
        "message_id": "<meeting-1@example.com>",
        "from": "Ahmed <ahmed@example.com>",
        "from_name": "Ahmed",
        "from_email": "ahmed@example.com",
        "to": "natasha@example.com",
        "subject": "Meeting tomorrow",
        "date": "Wed, 26 Aug 2026 17:41:52 +0500",
        "body": (
            "Hi Natasha,\n\n"
            "Can we have a quick call tomorrow around 3 PM?\n"
            "Please let me know if that works for you.\n\n"
            "Thanks,\n"
            "Ahmed"
        ),
    }

    result = EmailUnderstanding().analyze(message)

    assert result["intent"] == "meeting_request"
    assert result["time_reference"] == "tomorrow"
    assert result["should_reply"] is True


def test_meeting_draft_does_not_quote_entire_email():
    message = {
        "id": "meeting-2",
        "message_id": "<meeting-2@example.com>",
        "from": "Ahmed <ahmed@example.com>",
        "from_name": "Ahmed",
        "from_email": "ahmed@example.com",
        "to": "natasha@example.com",
        "subject": "Meeting tomorrow",
        "date": "Wed, 26 Aug 2026 17:41:52 +0500",
        "body": (
            "Can we have a quick call tomorrow around 3 PM?\n"
            "Please let me know if that works for you."
        ),
    }

    generator = ReplyGenerator(
        {
            "sender_name": "Natasha Roman",
            "sender_title": "Dispatch Operations Manager",
        }
    )

    draft = generator.draft(message)

    assert draft["analysis"]["intent"] == "meeting_request"
    assert "Can we have a quick call" not in draft["body"]
    assert "tomorrow" in draft["body"].lower()
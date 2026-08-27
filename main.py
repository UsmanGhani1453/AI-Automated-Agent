"""
CLI entry point.

Modes:
    python main.py
        Dry-run demo with simulated feedback.

    python main.py --live
        Actually send demo email via SMTP.

    python main.py --inbox
        Read unread Gmail messages and create local drafts.

    python main.py --learn-edit EMAIL_ID --edited-file FILE
        Teach the agent from a user-edited draft.

Inbox mode is read-only and draft-first.
It does not send, delete, or mark messages as read.
"""

from __future__ import annotations

import argparse
import random

from dotenv import load_dotenv

load_dotenv()

from app.agent.agent import Agent
from app.database.database import init_db
from app.database.repository import (
    EmailRepository,
    FeedbackRepository,
    LeadRepository,
    PatternRepository,
)
from app.email.reply_generator import ReplyGenerator
from app.learning.experience import Experience
from app.learning.learning_engine import LearningEngine
from app.memory.conversation import ConversationMemory
from app.memory.semantic import SemanticMemory
from app.tools.gmail_inbox import GmailInbox


DEMO_LEADS = [
    {
        "officer": "James",
        "company": "Redline Freight",
        "fleet_size": "1",
        "location": "Austin, TX",
        "email": "james@example.com",
        "category": "owner_operator",
    },
    {
        "officer": "Maria",
        "company": "Sunbelt Carriers",
        "fleet_size": "3",
        "location": "Dallas, TX",
        "email": "maria@example.com",
        "category": "small_fleet",
    },
    {
        "officer": "Tom",
        "company": "Coastal Hauling",
        "fleet_size": "1",
        "location": "Austin, TX",
        "email": "tom@example.com",
        "category": "owner_operator",
    },
    {
        "officer": "Linda",
        "company": "Pioneer Trucking",
        "fleet_size": "6",
        "location": "Houston, TX",
        "email": "linda@example.com",
        "category": "small_fleet",
    },
    {
        "officer": "Carlos",
        "company": "Vega Logistics",
        "fleet_size": "2",
        "location": "Austin, TX",
        "email": "carlos@example.com",
        "category": "owner_operator",
    },
    {
        "officer": "Sam",
        "company": "Northgate Freight",
        "fleet_size": "1",
        "location": "San Antonio, TX",
        "email": "sam@example.com",
        "category": "owner_operator",
    },
]


SENDER = {
    "sender_name": "Natasha Roman",
    "sender_title": "Dispatch Operations Manager",
    "sender_email": "natasha@example.com",
}


def simulate_feedback(strategy: str) -> dict:
    """
    Synthetic feedback used only by the offline/demo learning loop.
    """
    good_strategies = {
        "LOCATION_PERSONALIZED",
        "VALUE_FIRST",
    }

    base = 4 if strategy in good_strategies else 2

    rating = max(
        1,
        min(
            5,
            base + random.choice([-1, 0, 0, 1]),
        ),
    )

    replied = (
        strategy in good_strategies
        and random.random() < 0.4
    )

    return {
        "rating": rating,
        "replied": replied,
        "comment": "",
    }


def run_demo(args: argparse.Namespace) -> None:
    """
    Run the existing offline learning demonstration.
    """
    init_db()

    agent = Agent(
        sender_info=SENDER,
        dry_run=not args.live,
    )

    print("=" * 70)
    print(
        "Running agent over demo leads "
        "(dry_run=%s)" % (not args.live)
    )
    print(
        "Feedback is simulated but strategy-correlated, "
        "to demonstrate learning."
    )
    print("=" * 70)

    for round_num in range(
        1,
        args.rounds + 1,
    ):
        print(
            f"\n--- Learning round {round_num} ---"
        )

        for raw_lead in DEMO_LEADS:
            lead = agent.perceive(raw_lead)

            memory_context = (
                agent.understand_and_retrieve(
                    lead # type: ignore
                )
            )

            lead_decision, _ = agent.decide(
                lead, # type: ignore
                memory_context,
            )

            if lead_decision.action != "proceed":
                print(
                    f"  {lead['email']}: " # type: ignore
                    f"{lead_decision.action} "
                    f"({lead_decision.reason})"
                )
                continue

            agent.plan(
                "Contact new qualified lead."
            )

            generated = (
                agent.execute_generate_email(
                    lead # type: ignore
                )
            )

            agent.evaluate(
                generated["analyzer_report"]
            )

            agent.decide_on_email(
                generated["analyzer_report"]
            )

            email_id = EmailRepository.create(
                lead_id=lead["id"], # type: ignore
                strategy=generated["strategy"],
                components=generated["components"],
                body=generated["body"],
                quality_score=(
                    generated[
                        "analyzer_report"
                    ]["quality_score"]
                ),
                analyzer_report=(
                    generated[
                        "analyzer_report"
                    ]
                ),
            )

            generated["email_id"] = email_id

            feedback = simulate_feedback(
                generated["strategy"]
            )

            EmailRepository.approve(
                email_id
            )

            agent.send(
                lead, # type: ignore
                generated["body"],
            )

            EmailRepository.mark_sent(
                email_id
            )

            agent.learn(
                lead,
                generated,
                user_action="approve",
                rating=feedback["rating"],
                replied=feedback["replied"],
                outcome="sent",
            )

            print(
                f"  {lead['email']:22s} " # type: ignore
                f"strategy={generated['strategy']:22s} "
                f"quality="
                f"{generated['analyzer_report']['quality_score']:.2f} "
                f"rating={feedback['rating']} "
                f"replied={feedback['replied']}"
            )

    print("\n" + "=" * 70)
    print("Learned strategy scores after run:")
    print("=" * 70)

    for pattern in PatternRepository.all_for_prefix(
        "strategy:"
    ):
        print(
            f"  {pattern['pattern_key']:35s} "
            f"score={pattern['score']:.3f}  "
            f"samples={pattern['sample_count']}  "
            f"replies={pattern['reply_count']}"
        )

    print(
        "\nDerived semantic-memory statements:"
    )

    for statement in SemanticMemory().derive_statements(
        min_samples=2
    ):
        print(f"  - {statement}")


def run_inbox(limit: int) -> None:
    """
    Read unread Gmail messages and generate local drafts.

    No messages are sent, deleted, or marked as read.
    """
    init_db()

    print("=" * 70)
    print("GMAIL INBOX MODE — READ ONLY / DRAFT FIRST")
    print(
        "No messages will be sent, deleted, "
        "or marked as read."
    )
    print("=" * 70)

    inbox = GmailInbox()
    generator = ReplyGenerator(SENDER)
    conversations = ConversationMemory()

    messages = inbox.fetch_unread(
        limit=limit
    )

    if not messages:
        print("\nNo unread messages found.")
        return

    for index, message in enumerate(
        messages,
        start=1,
    ):
        context = conversations.ingest(
            message
        )

        draft = generator.draft(
            message,
            conversation_context=context,
        )

        body = message.get(
            "body",
            "",
        )

        preview = (
            body[:800]
            + (
                "..."
                if len(body) > 800
                else ""
            )
        )

        print(
            f"\n[{index}] "
            f"{message.get('from', '(unknown sender)')}"
        )

        print(
            f"Subject:    "
            f"{message.get('subject') or '(no subject)'}"
        )

        print(
            f"Date:       "
            f"{message.get('date') or '(unknown)'}"
        )

        print(
            f"Type:       "
            f"{draft['category']} — "
            f"{draft['reason']}"
        )

        analysis = draft.get(
            "analysis",
            {},
        )

        print(
            f"Intent:     "
            f"{analysis.get('intent', 'unknown')}"
        )

        print(
            f"Urgency:    "
            f"{analysis.get('urgency', 'unknown')}"
        )

        print(
            f"Thread:     "
            f"{context['thread_key']}"
        )

        print(
            f"Human decision required: "
            f"{draft.get('requires_human_decision', False)}"
        )

        requested_action = analysis.get(
            "requested_action",
            "",
        )

        if requested_action:
            print(
                f"Requested action: "
                f"{requested_action}"
            )

        print("\nIncoming message:")
        print(
            preview
            or "(no readable body detected)"
        )

        if draft["should_reply"]:
            print("\nAI draft:")
            print(draft["body"])
        else:
            print(
                "\nAI action: IGNORE — "
                "no reply draft generated"
            )

        print("\n" + "-" * 70)

    print(
        "\nDrafts were generated locally only. "
        "Nothing was sent."
    )


def run_learn_edit(
    email_id: int,
    edited_file: str,
) -> None:
    """
    Learn from a user-edited draft.

    The original AI draft is compared with the edited version.
    Extracted preferences are persisted in learned_preferences.
    """
    init_db()

    email_record = EmailRepository.get(
        email_id
    )

    if not email_record:
        raise RuntimeError(
            f"Email ID {email_id} was not found "
            "in the database."
        )

    edited_path = edited_file

    try:
        with open(
            edited_path,
            "r",
            encoding="utf-8",
        ) as handle:
            edited_body = handle.read().strip()
    except OSError as exc:
        raise RuntimeError(
            f"Could not read edited file "
            f"'{edited_path}': {exc}"
        ) from exc

    if not edited_body:
        raise RuntimeError(
            "Edited email is empty."
        )

    lead = LeadRepository.get(
        email_record["lead_id"]
    )

    if not lead:
        raise RuntimeError(
            f"Lead for email ID {email_id} "
            "was not found."
        )

    # Store the user's final version.
    EmailRepository.set_user_edit(
        email_id,
        edited_body,
    )

    # Store an explicit edit event.
    FeedbackRepository.create(
        email_id=email_id,
        rating=None,
        action="edit",
        comment="User edited draft",
        replied=False,
    )

    experience = Experience(
        lead=lead,
        strategy=(
            email_record.get("strategy")
            or "INBOX_REPLY"
        ),
        components=email_record.get(
            "components",
            {},
        ),
        generated_email=email_record.get(
            "body",
            "",
        ),
        analyzer_report=email_record.get(
            "analyzer_report",
            {},
        ),
        decision={
            "source": "manual_edit_learning",
            "email_id": email_id,
        },
        user_action="edit",
        user_edited_email=edited_body,
        rating=None,
        replied=False,
        comment="User edited draft",
        outcome="edited",
    )

    result = LearningEngine().learn(
        experience,
        email_id=email_id,
        component_ids=None,
    )

    print("=" * 70)
    print(
        f"LEARNED FROM EMAIL #{email_id}"
    )
    print("=" * 70)

    findings = result.get(
        "preference_findings",
        [],
    )

    if not findings:
        print(
            "\nNo new preference signals detected."
        )
        return

    print(
        "\nLearned preferences:"
    )

    for finding in findings:
        print(
            f"  {finding['key']}: "
            f"{finding['description']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Adaptive self-learning email agent"
        )
    )

    parser.add_argument(
        "--live",
        action="store_true",
        help=(
            "actually send demo email via SMTP"
        ),
    )

    parser.add_argument(
        "--rounds",
        type=int,
        default=3,
        help=(
            "how many times to loop "
            "the demo leads"
        ),
    )

    parser.add_argument(
        "--inbox",
        action="store_true",
        help=(
            "read unread Gmail messages "
            "and create draft replies"
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help=(
            "maximum unread inbox messages "
            "to load"
        ),
    )

    parser.add_argument(
        "--learn-edit",
        type=int,
        metavar="EMAIL_ID",
        help=(
            "learn from a user-edited "
            "email draft"
        ),
    )

    parser.add_argument(
        "--edited-file",
        type=str,
        help=(
            "text file containing the "
            "user's corrected email"
        ),
    )

    args = parser.parse_args()

    # --------------------------------------------------------------
    # Safety / argument validation
    # --------------------------------------------------------------

    if args.inbox and args.live:
        parser.error(
            "--inbox is read-only and cannot "
            "be combined with --live"
        )

    if (
        args.learn_edit is not None
        and args.inbox
    ):
        parser.error(
            "--learn-edit cannot be combined "
            "with --inbox"
        )

    if (
        args.learn_edit is None
        and args.edited_file
    ):
        parser.error(
            "--edited-file requires --learn-edit"
        )

    # --------------------------------------------------------------
    # Learn from user edit
    # --------------------------------------------------------------

    if args.learn_edit is not None:
        if not args.edited_file:
            parser.error(
                "--learn-edit requires "
                "--edited-file"
            )

        run_learn_edit(
            args.learn_edit,
            args.edited_file,
        )
        return

    # --------------------------------------------------------------
    # Gmail inbox
    # --------------------------------------------------------------

    if args.inbox:
        run_inbox(
            max(
                1,
                min(
                    args.limit,
                    50,
                ),
            )
        )
        return

    # --------------------------------------------------------------
    # Default demo
    # --------------------------------------------------------------

    run_demo(args)


if __name__ == "__main__":
    main()
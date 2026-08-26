"""
CLI entry point.

Modes:
    python main.py                 # dry-run demo with simulated feedback
    python main.py --live          # actually send demo email via SMTP
    python main.py --inbox         # read unread Gmail messages and create drafts

Inbox mode is read-only and draft-first. It does not send, delete, or mark
messages as read.
"""
import argparse
import random

from dotenv import load_dotenv

load_dotenv()

from app.database.database import init_db
from app.agent.agent import Agent
from app.database.repository import PatternRepository
from app.memory.semantic import SemanticMemory
from app.tools.gmail_inbox import GmailInbox
from app.email.reply_generator import ReplyGenerator


DEMO_LEADS = [
    {"officer": "James", "company": "Redline Freight", "fleet_size": "1", "location": "Austin, TX", "email": "james@example.com", "category": "owner_operator"},
    {"officer": "Maria", "company": "Sunbelt Carriers", "fleet_size": "3", "location": "Dallas, TX", "email": "maria@example.com", "category": "small_fleet"},
    {"officer": "Tom", "company": "Coastal Hauling", "fleet_size": "1", "location": "Austin, TX", "email": "tom@example.com", "category": "owner_operator"},
    {"officer": "Linda", "company": "Pioneer Trucking", "fleet_size": "6", "location": "Houston, TX", "email": "linda@example.com", "category": "small_fleet"},
    {"officer": "Carlos", "company": "Vega Logistics", "fleet_size": "2", "location": "Austin, TX", "email": "carlos@example.com", "category": "owner_operator"},
    {"officer": "Sam", "company": "Northgate Freight", "fleet_size": "1", "location": "San Antonio, TX", "email": "sam@example.com", "category": "owner_operator"},
]

SENDER = {
    "sender_name": "Natasha Roman",
    "sender_title": "Dispatch Operations Manager",
    "sender_email": "natasha@example.com",
}


def simulate_feedback(strategy):
    good_strategies = {"LOCATION_PERSONALIZED", "VALUE_FIRST"}
    base = 4 if strategy in good_strategies else 2
    rating = max(1, min(5, base + random.choice([-1, 0, 0, 1])))
    replied = strategy in good_strategies and random.random() < 0.4
    return {"rating": rating, "replied": replied, "comment": ""}


def run_demo(args):
    init_db()
    agent = Agent(sender_info=SENDER, dry_run=not args.live)

    print("=" * 70)
    print("Running agent over demo leads (dry_run=%s)" % (not args.live))
    print("Feedback is simulated but strategy-correlated, to demonstrate learning.")
    print("=" * 70)

    for round_num in range(1, args.rounds + 1):
        print(f"\n--- Learning round {round_num} ---")
        for raw_lead in DEMO_LEADS:
            lead = agent.perceive(raw_lead)
            memory_context = agent.understand_and_retrieve(lead)
            lead_decision, _ = agent.decide(lead, memory_context)
            if lead_decision.action != "proceed":
                print(f"  {lead['email']}: {lead_decision.action} ({lead_decision.reason})")
                continue

            agent.plan("Contact new qualified lead.")
            generated = agent.execute_generate_email(lead)
            agent.evaluate(generated["analyzer_report"])
            agent.decide_on_email(generated["analyzer_report"])

            from app.database.repository import EmailRepository
            email_id = EmailRepository.create(
                lead_id=lead["id"], strategy=generated["strategy"],
                components=generated["components"], body=generated["body"],
                quality_score=generated["analyzer_report"]["quality_score"],
                analyzer_report=generated["analyzer_report"],
            )
            generated["email_id"] = email_id

            feedback = simulate_feedback(generated["strategy"])
            EmailRepository.approve(email_id)
            agent.send(lead, generated["body"])
            EmailRepository.mark_sent(email_id)

            agent.learn(
                lead, generated, user_action="approve",
                rating=feedback["rating"], replied=feedback["replied"],
                outcome="sent",
            )

            print(
                f"  {lead['email']:22s} strategy={generated['strategy']:22s} "
                f"quality={generated['analyzer_report']['quality_score']:.2f} "
                f"rating={feedback['rating']} replied={feedback['replied']}"
            )

    print("\n" + "=" * 70)
    print("Learned strategy scores after run:")
    print("=" * 70)
    for p in PatternRepository.all_for_prefix("strategy:"):
        print(
            f"  {p['pattern_key']:35s} score={p['score']:.3f}  "
            f"samples={p['sample_count']}  replies={p['reply_count']}"
        )

    print("\nDerived semantic-memory statements:")
    for statement in SemanticMemory().derive_statements(min_samples=2):
        print(f"  - {statement}")


def run_inbox(limit: int):
    print("=" * 70)
    print("GMAIL INBOX MODE — READ ONLY / DRAFT FIRST")
    print("No messages will be sent, deleted, or marked as read.")
    print("=" * 70)

    inbox = GmailInbox()
    generator = ReplyGenerator(SENDER)
    messages = inbox.fetch_unread(limit=limit)

    if not messages:
        print("\nNo unread messages found.")
        return

    for index, message in enumerate(messages, start=1):
        draft = generator.draft(message)
        body = message.get("body", "")
        preview = body[:800] + ("..." if len(body) > 800 else "")

        print(f"\n[{index}] {message.get('from', '(unknown sender)')}")
        print(f"Subject: {message.get('subject') or '(no subject)'}")
        print(f"Date:    {message.get('date') or '(unknown)'}")
        print(f"Type:    {draft['category']} — {draft['reason']}")
        print("\nIncoming message:")
        print(preview or "(no readable body detected)")
        if draft["should_reply"]:
            print("\nAI draft:")
            print(draft["body"])
        else:
            print("\nAI action: IGNORE — no reply draft generated")
        print("\n" + "-" * 70)

    print("\nDrafts were generated locally only. Nothing was sent.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="actually send demo email via SMTP")
    parser.add_argument("--rounds", type=int, default=3, help="how many times to loop the demo leads")
    parser.add_argument("--inbox", action="store_true", help="read unread Gmail messages and create draft replies")
    parser.add_argument("--limit", type=int, default=10, help="maximum unread inbox messages to load")
    args = parser.parse_args()

    if args.inbox and args.live:
        parser.error("--inbox is read-only and cannot be combined with --live")

    if args.inbox:
        run_inbox(max(1, min(args.limit, 50)))
        return

    run_demo(args)


if __name__ == "__main__":
    main()

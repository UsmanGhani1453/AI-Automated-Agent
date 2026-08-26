"""
Demonstration / CLI entry point.

Runs the agent against a batch of leads in dry_run mode (no real email sent
unless SENDER_EMAIL/SENDER_APP_PASSWORD are set AND --live is passed), with
simulated feedback so you can watch the learning engine's scores move across
iterations without needing a human in the loop for every run.

Usage:
    python main.py                 # dry run demo with simulated feedback
    python main.py --live          # actually send via SMTP (reads .env)
"""
import argparse
import random
from dotenv import load_dotenv

load_dotenv()

from app.database.database import init_db
from app.agent.agent import Agent
from app.database.repository import PatternRepository
from app.memory.semantic import SemanticMemory

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
    """
    Fake but consistent feedback signal for the demo: pretend
    LOCATION_PERSONALIZED and VALUE_FIRST tend to perform better, so you can
    watch strategy_scores diverge over the run without needing real replies.
    """
    good_strategies = {"LOCATION_PERSONALIZED", "VALUE_FIRST"}
    base = 4 if strategy in good_strategies else 2
    rating = max(1, min(5, base + random.choice([-1, 0, 0, 1])))
    replied = strategy in good_strategies and random.random() < 0.4
    return {"rating": rating, "replied": replied, "comment": ""}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="actually send email via SMTP")
    parser.add_argument("--rounds", type=int, default=3, help="how many times to loop the demo leads")
    args = parser.parse_args()

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
            evaluation = agent.evaluate(generated["analyzer_report"])
            email_decision = agent.decide_on_email(generated["analyzer_report"])

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
            send_result = agent.send(lead, generated["body"])
            EmailRepository.mark_sent(email_id)

            agent.learn(
                lead, generated, user_action="approve",
                rating=feedback["rating"], replied=feedback["replied"],
                outcome="sent",
            )

            print(f"  {lead['email']:22s} strategy={generated['strategy']:22s} "
                  f"quality={generated['analyzer_report']['quality_score']:.2f} "
                  f"rating={feedback['rating']} replied={feedback['replied']}")

    print("\n" + "=" * 70)
    print("Learned strategy scores after run:")
    print("=" * 70)
    for p in PatternRepository.all_for_prefix("strategy:"):
        print(f"  {p['pattern_key']:35s} score={p['score']:.3f}  samples={p['sample_count']}  "
              f"replies={p['reply_count']}")

    print("\nDerived semantic-memory statements:")
    for s in SemanticMemory().derive_statements(min_samples=2):
        print(f"  - {s}")


if __name__ == "__main__":
    main()

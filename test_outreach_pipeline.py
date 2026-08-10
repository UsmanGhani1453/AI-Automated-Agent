"""
Local smoke test for outreach_pipeline.py's message-generation step,
using mocked lead data (skips the real scrape + real OpenAI call).

Run with:
    python test_outreach_pipeline.py
"""
from unittest.mock import patch

fake_leads = [
    {"name": "Randy Lopez", "company": "Lopez Trucking LLC", "fleet_size": "12", "email": "randy@example.com"},
    {"name": "Floriot Francois", "company": "FF Freight", "fleet_size": "5", "email": "floriot@example.com"},
]


class FakeChoice:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})


class FakeResponse:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]


def fake_create(*args, **kwargs):
    # Pull the lead name out of the prompt so the fake response looks tailored
    prompt = kwargs["messages"][1]["content"]
    return FakeResponse(f"[MOCK] Hi — quick note based on: {prompt.strip().splitlines()[-2].strip()}")


import outreach_pipeline as op

with patch("openai.chat.completions.create", side_effect=fake_create):
    for lead in fake_leads:
        msg = op.generate_personalized_message(lead)
        print("-" * 40)
        print(f"To: {lead['email']}")
        print(f"Body: {msg}")
        assert msg is not None, "Expected a generated message"

print("\n✅ outreach_pipeline generation test passed.")

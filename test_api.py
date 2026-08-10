"""
Local smoke test for my_api.py — exercises the full request flow
(lead in -> mock email generation -> dry-run 'send') without needing
a real trained model, Gmail credentials, or internet access.

Run with:
    DRY_RUN=true MOCK_GENERATOR=true python test_api.py
"""
import os

os.environ.setdefault("DRY_RUN", "true")
os.environ.setdefault("MOCK_GENERATOR", "true")
os.environ.setdefault("GMAIL_USER", "test@example.com")
os.environ.setdefault("GMAIL_APP_PASSWORD", "not-used-in-dry-run")

from fastapi.testclient import TestClient
from my_api import app

client = TestClient(app)

payload = {
    "officer": "RANDY LOPEZ",
    "email": "randy@example.com",
    "location": "MARIETTA, GA",
}

print("POST /process-lead with:", payload)
response = client.post("/process-lead", json=payload)

print("Status code:", response.status_code)
print("Response body:", response.json())

assert response.status_code == 200, "Expected 200 OK"
assert response.json()["status"] == "Lead processed and email queued"
print("\n✅ API test passed — request accepted and background task queued.")

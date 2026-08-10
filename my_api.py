from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests

app = FastAPI(title="Local Dispatch AI Service")

class LeadRequest(BaseModel):
    officer: str
    location: str
    company: str = ""
    fleet_size: str = "1"

@app.post("/generate-email")
def generate_email(lead: LeadRequest):
    try:
        # Prompt explicitly providing real sender info and instructing full email structure
        prompt = f"""Below is an instruction that describes a task, paired with an input that provides further context. Write a response that appropriately completes the request.

### Instruction:
Write a complete, formal, and professional outreach email for freight dispatching.
You MUST write out every detail with real information and NEVER use square brackets like [Your Name], [Company], or [Date].

SENDER DETAILS TO USE FOR SIGN-OFF:
- Name: Natasha Roman
- Title: Dispatch Operations Manager
- Email / Contact: natasharoman5667@gmail.com

EMAIL REQUIREMENTS:
1. Formal greeting addressing Officer {lead.officer}.
2. Body paragraphs offering dedicated dispatching services and freight lanes near {lead.location}.
3. A clear call to action asking to discuss details by this Friday.
4. Formal sign-off including Natasha Roman's full name, title, and contact email.
5. STRICT RULE: Do NOT use square brackets `[` or `]` anywhere. Do NOT include "Subject:" in the body.

### Input:
Officer: {lead.officer}, Location: {lead.location}, Company: {lead.company}

### Response:"""

        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "gemma2:2b",
                "prompt": prompt,
                "stream": False
            }
        )
                 
        result = response.json()
        generated_text = result.get("response", "").strip()

        # Clean up any leftover Subject headers
        lines = [line for line in generated_text.splitlines() if not line.strip().startswith("**Subject:") and not line.strip().startswith("Subject:")]
        clean_email = "\n".join(lines).strip()

        return {
            "status": "success",
            "officer": lead.officer,
            "generated_email": clean_email
        }
             
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
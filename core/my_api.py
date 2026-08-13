from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
from typing import List
import requests
import json
import os
import smtplib
from email.message import EmailMessage

app = FastAPI(title="Local Dispatch AI Service")

class TargetLead(BaseModel):
    recipient_email: EmailStr
    officer: str
    location: str
    company: str = "Natasha & co"
    fleet_size: str = "1"

class DispatchCampaignRequest(BaseModel):
    login_url: str
    sender_email: EmailStr
    sender_password: str
    leads: List[TargetLead]

@app.post("/generate-and-send")
def process_campaign(campaign: DispatchCampaignRequest):
    processed_emails = []

    # 1. Load examples from JSON file
    examples_text = ""
    file_path = "examples.json"
    
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            examples = data.get("examples", [])
            for i, ex in enumerate(examples, 1):
                examples_text += f"---EXAMPLE {i}---\n"
                examples_text += f"Input Context:\nOfficer: {ex['officer']}\nLocation: {ex['location']}\nCompany: {ex['company']}\nFleet Size: {ex['fleet_size']}\n\n"
                examples_text += f"Perfect Email Output:\n{ex['email_body']}\n\n"

    # 2. Connect to Gmail using SMTP_SSL on Port 465 (More reliable)
    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(campaign.sender_email, campaign.sender_password)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GMAIL CONNECTION ERROR: {str(e)}")

    try:
        # 3. Loop through every lead
        for lead in campaign.leads:
            prompt = f"""Here are examples of perfect, professional freight dispatching outreach emails.

{examples_text}
CRITICAL RULES:
1. Always sign off the email with the name "Natasha Roman", the title "Dispatch Operations Manager", and the email "{campaign.sender_email}".
2. NEVER use placeholders like [Your Name] or [Your Email].
3. Do NOT include a subject line.
4. OUTPUT ONLY THE EMAIL BODY. Do NOT add any explanations, notes, reasoning, or conversational follow-ups like "Let me know if you'd like more examples".

Input Context:
Officer: {lead.officer}
Location: {lead.location}
Company: {lead.company}
Fleet Size: {lead.fleet_size}

Perfect Email Output:"""

            # Call Ollama LLM
            try:
                response = requests.post(
                    "http://localhost:11434/api/generate",
                    json={
                        "model": "gemma2:2b",
                        "prompt": prompt,
                        "stream": False
                    },
                    timeout=60 # Prevent hanging forever
                )
            except Exception as e:
                server.quit()
                raise HTTPException(status_code=500, detail=f"OLLAMA AI ERROR: {str(e)}")
                     
            result = response.json()
            generated_text = result.get("response", "").strip()

            # Clean the text
            for marker in ["**Explanation:", "Explanation:", "**Note:", "Note:", "Let me know if"]:
                if marker in generated_text:
                    generated_text = generated_text.split(marker)[0].strip()

            lines = [line for line in generated_text.splitlines() if not line.strip().startswith("**Subject:") and not line.strip().startswith("Subject:")]
            clean_email = "\n".join(lines).strip()

            # 4. Construct the physical email object
            msg = EmailMessage()
            msg.set_content(clean_email)
            msg["Subject"] = f"Freight Dispatching Services near {lead.location}" 
            msg["From"] = campaign.sender_email
            msg["To"] = lead.recipient_email

            # 5. Send the message
            try:
                server.send_message(msg)
            except Exception as e:
                server.quit()
                raise HTTPException(status_code=500, detail=f"GMAIL SEND ERROR: {str(e)}")

            processed_emails.append({
                "recipient_email": lead.recipient_email,
                "officer": lead.officer,
                "location": lead.location,
                "generated_email": clean_email
            })

        # Close the server connection when finished
        server.quit()

        return {
            "status": "success",
            "sender_account": campaign.sender_email,
            "login_url": campaign.login_url,
            "total_sent": len(processed_emails),
            "results": processed_emails
        }

    except HTTPException:
        raise
    except Exception as e:
        try:
            server.quit()
        except:
            pass
        raise HTTPException(status_code=500, detail=f"GENERAL ERROR: {str(e)}")
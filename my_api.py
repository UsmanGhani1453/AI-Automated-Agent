from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from transformers import pipeline
import smtplib
from email.message import EmailMessage

app = FastAPI(title="Trucking Dispatch Agent API")

# Load your local trained model
generator = pipeline("text-generation", model="./your-trained-model-folder")

# Your Google App Password credentials
GMAIL_USER = "your_personal_email@gmail.com"
GMAIL_APP_PASSWORD = "your-16-character-app-password"

class LeadData(BaseModel):
    officer: str
    email: str
    location: str

def send_gmail(recipient_email: str, subject: str, body: str):
    """Handles the secure SMTP connection to Gmail."""
    msg = EmailMessage()
    msg.set_content(body)
    msg['Subject'] = subject
    msg['From'] = GMAIL_USER
    msg['To'] = recipient_email

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.send_message(msg)
            print(f"Email successfully sent to {recipient_email}")
    except Exception as e:
        print(f"Failed to send email to {recipient_email}: {e}")

@app.post("/process-lead")
def process_lead(lead: LeadData, background_tasks: BackgroundTasks):
    """Receives data from the scraper, generates the email, and sends it."""
    
    # 1. Generate the personalized email using your AI model
    prompt = f"Officer: {lead.officer}, Location: {lead.location}"
    result = generator(prompt, max_new_tokens=60, num_return_sequences=1)
    email_body = result[0]['generated_text']
    
    # 2. Dispatch the email in the background so the API doesn't hang
    background_tasks.add_task(
        send_gmail, 
        recipient_email=lead.email, 
        subject=f"Dispatching routes out of {lead.location}", 
        body=email_body
    )
    
    return {"status": "Lead processed and email queued", "target": lead.email}
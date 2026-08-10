import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
import core.scraper as scraper

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "natasharoman5667@gmail.com"
SENDER_PASSWORD = "xqttjpymnocymvec" 

def send_gmail(recipient_email, subject, body):
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = recipient_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, recipient_email, msg.as_string())
        server.quit()
        print(f"Successfully sent email to {recipient_email}")
    except Exception as e:
        print(f"Failed to send email: {e}")

def run_pipeline():
    print("Running scraper to fetch live leads...")
    leads = scraper.scrape_truckerdb()
    print(f"Successfully grabbed {len(leads)} leads. Processing through local AI...")

    for lead in leads:
        try:
            response = requests.post(
                "http://127.0.0.1:8000/generate-email",
                json={
                    "officer": lead["officer"].title(),
                    "location": lead["location"].title(),
                    "company": lead.get("company", "").title(),
                    "fleet_size": str(lead.get("fleet_size", "1"))
                }
            )
            
            result = response.json()
            generated_content = result.get("generated_email")
            
            if generated_content:
                print(f"Generated email for {lead['officer']}. Sending to {lead['email']}...")
                subject = f"Dispatching Opportunity - {lead['location'].title()}"
                
                send_gmail(lead["email"], subject, generated_content)
                
            time.sleep(2)
            
        except Exception as e:
            print(f"Error processing lead {lead['officer']}: {e}")

if __name__ == "__main__":
    run_pipeline()
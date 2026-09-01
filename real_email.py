import os
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

sender = os.getenv("SENDER_EMAIL")
password = os.getenv("SENDER_APP_PASSWORD")

recipient = "usmanghanivhr1453@gmail.com"

msg = MIMEText("Hello, this is a real test email from my Adaptive Email Agent.")
msg["Subject"] = "Test Email"
msg["From"] = sender
msg["To"] = recipient

with smtplib.SMTP("smtp.gmail.com", 587) as server:
    server.starttls()
    server.login(sender, password)
    server.sendmail(sender, recipient, msg.as_string())

print("Email sent successfully!")
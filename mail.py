import os
import requests
from dotenv import load_dotenv

load_dotenv("MAIL.env")

API_KEY = os.getenv("MAIL_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM")

def send_confirmation_email(to_email: str, name: str, role: str):
    try:
        url = "https://api.mailersend.com/v1/email"

        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }

        data = {
            "from": {
                "email": EMAIL_FROM,
                "name": "Gdynia Science Slam"
            },
            "to": [
                {
                    "email": to_email,
                    "name": name
                }
            ],
            "subject": "Potwierdzenie rejestracji na Gdynia Science Slam 2026",
            "text": f"Cześć {name}! Twoje zgłoszenie na {role} zostało zapisane. Dziękujemy!",
            "html": f"""
                <h2>Cześć {name}!</h2>
                <p>Twoje zgłoszenie na <strong>{role}</strong> zostało zapisane.</p>
                <p>Dziękujemy!</p>
            """
        }

        response = requests.post(url, headers=headers, json=data)

        if response.status_code >= 400:
            print("MailerSend error:", response.text)

    except Exception as e:
        print("Email sending failed:", e)
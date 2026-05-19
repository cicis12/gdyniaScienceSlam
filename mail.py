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
                <br>
                <h3>Informacje o wydarzeniu</h3>
                <p><strong>Lokalizacja:</strong> Pomorski Park Naukowo-Technologiczny - Budynek III (Centrum konferencyjne)</p>
                <p>Aleja Zwycięstwa 96/98 bud. 3, 81-451 Gdynia</p>
                <p>Wejście tak jak do Centrum Nauki Experyment. Po wejściu do budynku szatnia i rejestracja po prawej stronie (Centrum Konferencyjne).</p>
                <img src="https://ppnt.pl/wp-content/uploads/map-1.png" style="max-width: 100%; width: 100%; height: auto; display: block;">
                
                <p><strong>Terminarz:</strong></p>
                <p>9:30-10:00 Rejestracja</p>
                <p>10:00-11:00 Otwarcie Wydarzenia</p>
                <p>11:00-11:45 Pierwszy blok prelekcji (3 prelegentów)</p>
                <p>11:45-12:00 Przerwa</p>
                <p>12:00-12:45 Drugi blok prelekcji (3 prelegentów)</p>
                <p>12:45-13:15 Przerwa</p>
                <p>13:15-14:00 Trzeci blok prelekcji (3 prelegentów)</p>
                <p>14:00-14:20 Gościnny wykład chemiczny</p>
                <p>14:20-15:00 Czwarty blok prelekcji (2 prelegentów)</p>
                <p>15:00-15:30 Przerwa i głosowanie publiczności</p>
                <p>15:30-16:30 Zakończenie i ogłoszenie wyników</p>

                <p>Stanowisko rejestracji będzie czynne <strong>przez cały czas trwania wydarzenia</strong>. Wejście na wydarzenie jest możliwe w dowolnym momencie.</p>
                <p>Jeśli są Państwo grupą szkolną i planują się Państwo pojawić po 10, w miare możliwości prosimy zgłosić taki zamiar drogą mailową na <strong>gdyniascienceslam@gmail.com</strong>
            """
        }

        response = requests.post(url, headers=headers, json=data)

        if response.status_code >= 400:
            print("MailerSend error:", response.text)

    except Exception as e:
        print("Email sending failed:", e)
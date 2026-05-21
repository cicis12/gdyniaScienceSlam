from database import SessionLocal
from models import Voter
from security import hash_password
import getpass
from passlib.context import CryptContext
db = SessionLocal()

email = input("Email: ")

voter = Voter(
    email=email,
)
db.add(voter)
db.commit()
db.close()

print("Email added!")
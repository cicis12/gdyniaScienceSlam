from database import SessionLocal
from models import AdminUser
from security import hash_password
import getpass
from passlib.context import CryptContext
db = SessionLocal()

username = input("Username: ")
password = getpass.getpass("Password: ")

admin = AdminUser(
    username=username,
    password_hash=hash_password(password)
)
db.add(admin)
db.commit()
db.close()

print("Admin created!")
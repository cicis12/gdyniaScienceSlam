from database import SessionLocal
from models import AdminUser
from security import hash_password
import getpass
from passlib.context import CryptContext
db = SessionLocal()

username = input("Username: ")

user = (db.query(AdminUser).filter(AdminUser.username == username).first())
if not user:
    print("No such user")
    exit()

if user.is_superadmin:
    ans = input("Do you want to disable superadmin permissions of this user? (Y/n)")
    if ans.lower() == "n":
        print("Action aborted.")
        exit()
    user.is_superadmin = False
    db.commit()
    db.close()
    print("Disabled superadmin presmissions for this user.")
else:
    ans = input("Do you want to enable superadmin permissions of this user? (Y/n)")
    if ans.lower() == "n":
        print("Action aborted.")
        exit()
    user.is_superadmin = True
    db.commit()
    db.close()
    print("Enabled superadmin presmissions for this user.")


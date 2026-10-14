"""Toggle sysadmin access with the same prompts as make_superadmin.py."""
from database import SessionLocal
from models import AdminUser
from admin_sessions import revoke_admin_sessions


def main():
    username = input('Username: ')
    with SessionLocal() as db:
        user = db.query(AdminUser).filter(AdminUser.username == username).first()
        if not user:
            print('No such user')
            return
        action = 'disable' if user.is_sysadmin else 'enable'
        answer = input(f'Do you want to {action} sysadmin permissions of this user? (Y/n)')
        if answer.lower() == 'n':
            print('Action aborted.')
            return
        user.is_sysadmin = not user.is_sysadmin
        revoke_admin_sessions(db, user.id)
        db.commit()
        print(f'{"Enabled" if user.is_sysadmin else "Disabled"} sysadmin permissions for this user.')


if __name__ == '__main__':
    main()

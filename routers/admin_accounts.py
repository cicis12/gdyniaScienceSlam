"""Account administration, restricted to sysadmins."""
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from admin_sessions import check_csrf, revoke_admin_sessions
from database import get_db
from models import AdminUser
from security import hash_password
from templating import create_templates

templates = create_templates()


def build_router(require_sysadmin):
    router = APIRouter(prefix='/admin/admins', dependencies=[Depends(require_sysadmin)])

    def page(request, db, admin, error=None, status=200):
        return templates.TemplateResponse(request, 'admin/accounts.html', {
            'request': request, 'admin': admin, 'accounts': db.query(AdminUser).order_by(AdminUser.username).all(),
            'error': error,
        }, status_code=status)

    def validate_password(password):
        if len(password) < 12 or len(password.encode()) > 72:
            raise ValueError('Hasło musi mieć co najmniej 12 znaków i najwyżej 72 bajty.')

    @router.get('')
    def accounts(request: Request, db: Session = Depends(get_db), admin=Depends(require_sysadmin)):
        return page(request, db, admin)

    @router.post('/create')
    def create(request: Request, username: str = Form(...), password: str = Form(...),
               csrf: str = Form(...), is_superadmin: bool = Form(False),
               db: Session = Depends(get_db), admin=Depends(require_sysadmin)):
        check_csrf(request, csrf)
        username = username.strip()
        try:
            if not username or len(username) > 100 or any(ord(ch) < 32 for ch in username):
                raise ValueError('Podaj nazwę użytkownika o długości od 1 do 100 znaków.')
            validate_password(password)
            db.add(AdminUser(username=username, password_hash=hash_password(password),
                             is_active=True, is_superadmin=is_superadmin, is_sysadmin=False))
            db.commit()
        except ValueError as error:
            return page(request, db, admin, str(error), 422)
        except IntegrityError:
            db.rollback()
            return page(request, db, admin, 'Ta nazwa użytkownika jest już zajęta.', 409)
        return RedirectResponse('/admin/admins', 303)

    def target_account(db, account_id):
        # Lock the sysadmin set in a consistent order to preserve an active account
        # even when two administrators edit each other's accounts concurrently.
        db.query(AdminUser).filter_by(is_sysadmin=True).order_by(AdminUser.id).populate_existing().with_for_update().all()
        account = db.query(AdminUser).filter_by(id=account_id).with_for_update().first()
        if not account:
            raise HTTPException(404, 'Nie znaleziono konta.')
        return account

    @router.post('/{account_id}/update')
    def update(account_id: int, request: Request, csrf: str = Form(...),
               is_active: bool = Form(False), is_superadmin: bool = Form(False),
               password: str = Form(''), db: Session = Depends(get_db), admin=Depends(require_sysadmin)):
        check_csrf(request, csrf)
        account = target_account(db, account_id)
        if account.is_sysadmin and account.is_active and not is_active and db.query(AdminUser).filter_by(is_sysadmin=True, is_active=True).count() <= 1:
            return page(request, db, admin, 'Musi pozostać co najmniej jeden aktywny administrator systemowy.', 422)
        if account.id == admin.id and not is_active:
            return page(request, db, admin, 'Nie możesz wyłączyć własnego konta.', 422)
        if password:
            try:
                validate_password(password)
            except ValueError as error:
                return page(request, db, admin, str(error), 422)
            account.password_hash = hash_password(password)
        changed = (account.is_active != is_active or account.is_superadmin != is_superadmin or bool(password))
        account.is_active, account.is_superadmin = is_active, is_superadmin
        if changed:
            revoke_admin_sessions(db, account.id)
        db.commit()
        return RedirectResponse('/admin/admins', 303)

    @router.post('/{account_id}/delete')
    def delete(account_id: int, request: Request, csrf: str = Form(...),
               db: Session = Depends(get_db), admin=Depends(require_sysadmin)):
        check_csrf(request, csrf)
        account = target_account(db, account_id)
        if account.is_sysadmin and account.is_active and db.query(AdminUser).filter_by(is_sysadmin=True, is_active=True).count() <= 1:
            return page(request, db, admin, 'Musi pozostać co najmniej jeden aktywny administrator systemowy.', 422)
        if account.id == admin.id:
            return page(request, db, admin, 'Nie możesz usunąć własnego konta.', 422)
        revoke_admin_sessions(db, account.id)
        db.delete(account)
        db.commit()
        return RedirectResponse('/admin/admins', 303)

    return router

"""Opaque, revocable admin sessions. No credentials are placed in cookies."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import hmac
import secrets

from fastapi import HTTPException
from models import AdminSession, AdminUser

SESSION_SECONDS = 4 * 60 * 60


def fingerprint(value):
    return sha256(value.encode()).hexdigest()


def create_admin_session(db, admin):
    token = secrets.token_urlsafe(32)
    db.query(AdminSession).filter(AdminSession.expires_at <= datetime.now(timezone.utc).replace(tzinfo=None)).delete()
    db.add(AdminSession(token_hash=fingerprint(token), admin_id=admin.id,
                        password_fingerprint=fingerprint(admin.password_hash),
                        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=SESSION_SECONDS)))
    db.commit()
    return token


def session_admin(db, token):
    if not token or len(token) > 128:
        raise HTTPException(401)
    session = db.get(AdminSession, fingerprint(token))
    if not session or session.expires_at <= datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(401)
    admin = db.get(AdminUser, session.admin_id)
    if (not admin or not admin.is_active or
            not hmac.compare_digest(session.password_fingerprint, fingerprint(admin.password_hash))):
        raise HTTPException(401)
    return admin


def revoke_admin_sessions(db, admin_id):
    db.query(AdminSession).filter_by(admin_id=admin_id).delete()


def csrf_token(request):
    # A session-bound token that does not expose the HttpOnly session cookie.
    token = request.cookies.get('admin_session', '')
    return hmac.new(token.encode(), b'admin-csrf', 'sha256').hexdigest() if token else ''


def check_csrf(request, value):
    expected = csrf_token(request)
    if not expected or not hmac.compare_digest(expected, value):
        raise HTTPException(403, 'Sesja formularza wygasła. Odśwież stronę i spróbuj ponownie.')

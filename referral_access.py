"""Separate partner-page entitlement from optional UUID analytics consent."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import os
from uuid import UUID

from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, Field

from models import InteractionLink, SystemSetting

SETTINGS_KEY = 'referral_popup'
ACCESS_COOKIE = 'gss_partner_access'
CONSENT_COOKIE = 'gss_tracking_consent'
COOKIE_HOURS = 24


class ReferralPopup(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    title: str = Field(default='Statystyki odwiedzin', min_length=1, max_length=160)
    content: str = Field(default='<p>Czy zgadzasz się na zbieranie statystyk czasu oglądania sekcji, kliknięć i otwarć FAQ dla tego linku?</p><p>Odmowa nie ograniczy dostępu do strony dla partnerów.</p>', min_length=1, max_length=10000)
    accept_label: str = Field(default='Tak, zgadzam się', min_length=1, max_length=80)
    reject_label: str = Field(default='Nie, dziękuję', min_length=1, max_length=80)

    @property
    def revision(self):
        return sha256(self.model_dump_json().encode()).hexdigest()


def get_popup(db):
    setting = db.get(SystemSetting, SETTINGS_KEY)
    return ReferralPopup.model_validate_json(setting.value) if setting else ReferralPopup()


def decode_cookie(token, purpose):
    if not token:
        return {}
    try:
        data = jwt.decode(token, os.environ['SECRET_KEY'], algorithms=['HS256'])
        return data if data.get('purpose') == purpose else {}
    except (JWTError, ValueError, TypeError):
        return {}


def signed_cookie(data, purpose):
    return jwt.encode({**data, 'purpose': purpose,
                       'exp': datetime.now(timezone.utc) + timedelta(hours=COOKIE_HOURS)},
                      os.environ['SECRET_KEY'], algorithm='HS256')


def active_link(db, raw):
    try:
        link_id = str(UUID(str(raw)))
    except (ValueError, TypeError, AttributeError):
        return None
    link = db.get(InteractionLink, link_id)
    return link if link is not None and link.active else None


def referral_context(db, request):
    popup = get_popup(db)
    access = decode_cookie(request.cookies.get(ACCESS_COOKIE), 'partner-access').get('access') is True
    consent = decode_cookie(request.cookies.get(CONSENT_COOKIE), 'tracking-consent')
    # An explicitly supplied unknown/disabled UUID must not fall back to an old
    # consent UUID and attribute a new invitation to the wrong link.
    raw = request.query_params.get('ref')
    link = active_link(db, raw) if raw is not None else active_link(db, consent.get('link_id')) if consent else None
    consented = bool(link and consent.get('link_id') == link.id and consent.get('revision') == popup.revision)
    return {'popup': popup, 'link_id': link.id if link else None,
            'access': access or link is not None,
            'consented': consented, 'needs_popup': link is not None and not consented}


def consent_matches(db, request, link_id):
    consent = decode_cookie(request.cookies.get(CONSENT_COOKIE), 'tracking-consent')
    return consent.get('link_id') == str(link_id) and consent.get('revision') == get_popup(db).revision


def set_access_cookie(response, request):
    response.set_cookie(ACCESS_COOKIE, signed_cookie({'access': True}, 'partner-access'),
                        httponly=True, secure=request.url.scheme == 'https', samesite='lax', path='/')

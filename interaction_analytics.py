"""Privacy-minimizing, cumulative section counters; no visitor content or IP storage."""
from datetime import datetime, timedelta, timezone
import re

from models import InteractionVisit, InteractionSection, SystemSetting
from site_pages import PUBLIC_PAGES

ENABLED_KEY = 'interaction_tracking_enabled'
RETENTION_DAYS = 90
PUBLIC_PATHS = {path for _, path, _ in PUBLIC_PAGES}
PAGE_LABELS = {path: label for _, path, label in PUBLIC_PAGES}


def public_html_path(path):
    return isinstance(path, str) and (path in PUBLIC_PATHS or re.fullmatch(r'/forms/[a-zA-Z0-9_-]{1,160}', path) is not None)


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def tracking_enabled(db):
    setting = db.get(SystemSetting, ENABLED_KEY)
    return setting is not None and setting.value == 'true'


def prune(db):
    expired = db.query(InteractionVisit.id).filter(InteractionVisit.created_at < utc_now() - timedelta(days=RETENTION_DAYS))
    db.query(InteractionSection).filter(InteractionSection.visit_id.in_(expired)).delete(synchronize_session=False)
    db.query(InteractionVisit).filter(InteractionVisit.id.in_(expired)).delete(synchronize_session=False)


def section_label(db, path, key):
    if key == 'page':
        return 'Cała strona'
    if path == '/':
        return {'hero': 'Wprowadzenie', 'about': 'O nas', 'team': 'Zespół', 'archive': 'Poprzednie edycje',
                'partners': 'Partnerzy', 'become_partner': 'Zostań partnerem'}.get(key, key)
    if path == '/become-a-partner':
        from partnership_content import get_partnership
        section = next((s for s in get_partnership(db).sections if 'section-' + s.id == key), None)
        if section:
            return section.title or section.type
    if path == '/about':
        from about_content import get_timeline
        if key == 'benefits-title':
            return 'Dlaczego warto wziąć udział?'
        entry = next((s for s in get_timeline(db) if 'stage-' + s.id == key), None)
        if entry:
            return entry.title
    if path == '/partners':
        from partner_content import get_partners
        section = next((s for s in get_partners(db).sections if 'partners-' + s.id == key), None)
        if section:
            return section.title
    if key.startswith(('edition-', 'documents-')):
        return 'Edycja ' + key.rsplit('-', 1)[-1]
    return {'team-members': 'Członkowie zespołu', 'team-intro': 'Wprowadzenie',
            'team-profile': 'Profil członka zespołu', 'introduction': 'Wprowadzenie',
            'talks': 'Prelekcje', 'video': 'Film', 'registration': 'Rejestracja'}.get(key, key)

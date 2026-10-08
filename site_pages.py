"""Public page registry shared by navigation and visibility enforcement."""
from models import SystemSetting

PUBLIC_PAGES = (
    ('home', '/', 'Home'),
    ('team', '/team', 'Team'),
    ('about', '/about', 'O Nas'),
    ('previous_editions', '/previous_editions', 'Poprzednie edycje'),
    ('topics', '/topics', 'Tematy prelekcji'),
    ('partners', '/partners', 'Partnerzy'),
    ('documents', '/documents', 'Dokumenty'),
    ('registration', '/registration', 'Rejestracja'),
    ('vote', '/vote', 'Głosowanie'),
)


def page_visibility(db):
    settings = dict(db.query(SystemSetting.key, SystemSetting.value).filter(
        SystemSetting.key.like('page_visible:%')
    ).all())
    return {key: settings.get('page_visible:' + key, 'true') != 'false'
            for key, _, _ in PUBLIC_PAGES}


def page_for_path(path):
    path = path.rstrip('/') or '/'
    if path.startswith('/documents/'):
        return 'documents'
    if path.startswith('/vote/'):
        return 'vote'
    if path.startswith('/forms/') or path == '/api/forms/submit':
        return 'registration'
    return next((key for key, url, _ in PUBLIC_PAGES if url == path), None)

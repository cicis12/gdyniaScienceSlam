"""Shared templates with content-versioned local assets."""
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

from fastapi.templating import Jinja2Templates
from system_settings import DEFAULT_THEME, DEFAULT_FOOTER, DEFAULT_HOME, DEFAULT_PAGE_MODES

from site_pages import PUBLIC_PAGES, page_for_path

BASE_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=64)
def _asset_digest(path: Path, modified: int, size: int):
    return sha256(path.read_bytes()).hexdigest()[:12]


def asset_url(filename: str):
    path = BASE_DIR / 'static' / filename
    stat = path.stat()
    return f'/static/{filename}?v={_asset_digest(path, stat.st_mtime_ns, stat.st_size)}'


def public_page_key(request, page_name=''):
    if page_name in {key for key, _, _ in PUBLIC_PAGES}:
        return page_name
    return page_for_path(getattr(getattr(request, 'url', None), 'path', '')) or ''


def page_display_mode(request, page_name=''):
    settings = getattr(getattr(request, 'state', None), 'site_settings', {})
    return settings.get('page_modes', DEFAULT_PAGE_MODES).get(public_page_key(request, page_name), 'default')


def create_templates():
    templates = Jinja2Templates(directory=str(BASE_DIR / 'templates'))
    templates.env.globals['asset_url'] = asset_url
    templates.env.globals['public_page_key'] = public_page_key
    templates.env.globals['page_display_mode'] = page_display_mode
    templates.env.globals['default_site_settings'] = {'theme': DEFAULT_THEME, 'footer': DEFAULT_FOOTER, 'home': DEFAULT_HOME, 'page_modes': DEFAULT_PAGE_MODES}
    return templates

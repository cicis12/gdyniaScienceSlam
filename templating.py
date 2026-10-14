"""Shared templates with content-versioned local assets."""
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

from fastapi.templating import Jinja2Templates
from html_content import clean_html, safe_html
from admin_sessions import csrf_token
from file_types import file_accept, file_category_labels, FILE_CATEGORIES
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
    return 'default' if public_page_key(request, page_name) == 'home' else 'dark'


def create_templates():
    templates = Jinja2Templates(directory=str(BASE_DIR / 'templates'))
    templates.env.filters['safe_html'] = safe_html
    templates.env.filters['clean_html'] = clean_html
    templates.env.globals['csrf_token'] = csrf_token
    templates.env.globals['file_accept'] = file_accept
    templates.env.globals['file_category_labels'] = file_category_labels
    templates.env.globals['file_category_choices'] = [(key, value[0]) for key, value in FILE_CATEGORIES.items()]
    templates.env.globals['asset_url'] = asset_url
    templates.env.globals['public_page_key'] = public_page_key
    templates.env.globals['page_display_mode'] = page_display_mode
    templates.env.globals['default_site_settings'] = {'theme': DEFAULT_THEME, 'footer': DEFAULT_FOOTER, 'home': DEFAULT_HOME, 'page_modes': DEFAULT_PAGE_MODES}
    return templates

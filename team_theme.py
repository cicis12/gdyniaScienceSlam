"""Validated, persistent palette for the public team page."""
import json
import re

from models import SystemSetting

PALETTE_KEY = 'team_palette'
DETAILS_KEY = 'team_details_enabled'
COLOR_FIELDS = (
    ('background', 'Tło strony', '#132e46'),
    ('text', 'Tekst główny', '#f7ecda'),
    ('muted', 'Tekst wprowadzenia', '#d3e1e7'),
    ('accent', 'Akcent i licznik osób', '#99dccb'),
    ('highlight', 'Wyróżnienie nagłówka', '#ffc58c'),
    ('card_text', 'Tekst na kartach', '#132e46'),
    ('card_1', 'Karta 1', '#99dccb'),
    ('card_2', 'Karta 2', '#ffc58c'),
    ('card_3', 'Karta 3', '#c7b8ed'),
    ('card_4', 'Karta 4', '#efb6bc'),
)
DEFAULT_PALETTE = {key: value for key, _, value in COLOR_FIELDS}


def team_details_enabled(db):
    setting = db.get(SystemSetting, DETAILS_KEY)
    return setting is None or setting.value != 'false'


def valid_color(value):
    return isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value) is not None


def get_team_palette(db):
    setting = db.get(SystemSetting, PALETTE_KEY)
    try:
        saved = json.loads(setting.value) if setting else {}
    except (ValueError, TypeError):
        saved = {}
    if not isinstance(saved, dict):
        saved = {}
    return {key: saved[key].lower() if valid_color(saved.get(key)) else default
            for key, default in DEFAULT_PALETTE.items()}

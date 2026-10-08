"""Shared public colors, footer markup, and editable homepage copy."""
import json
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Comment
from models import SystemSetting
from site_pages import PUBLIC_PAGES
from team_theme import valid_color

THEME_KEY = 'site_theme'
FOOTER_KEY = 'site_footer'
HOME_KEY = 'home_content'
PAGE_MODES_KEY = 'page_display_modes'
DEFAULT_PAGE_MODES = {key: 'default' for key, _, _ in PUBLIC_PAGES if key != 'home'}
DISPLAY_MODES = {'default', 'light', 'dark'}
COLOR_GROUPS = (
    ('header', 'Nagłówek', (
        ('background', 'Tło', '#06101d'), ('text', 'Tekst', '#dde5ee'),
        ('logo', 'Logo', '#ffffff'), ('button', 'Przycisk', '#6afbfb'),
        ('button_text', 'Tekst przycisku', '#06101d'),)),
    ('footer', 'Stopka', (
        ('background', 'Tło', '#06101d'), ('text', 'Tekst', '#dde5ee'),
        ('small_text', 'Mały tekst', '#42628a'), ('link', 'Link', '#6afbfb'),
        ('border', 'Obramowanie', '#049595'),)),
    ('light', 'Jasne', (
        ('background', 'Tło', '#d5e2f6'), ('text', 'Tekst', '#324a67'),
        ('heading', 'Nagłówek główny', '#06101d'), ('secondary_heading', 'Nagłówek drugorzędny', '#122c54'),
        ('overline', 'Nadtytuł', '#223d77'), ('button', 'Przycisk', '#2d519f'),
        ('button_text', 'Tekst przycisku', '#ffffff'), ('link', 'Link', '#2d519f'),
        ('surface', 'Tło kart i formularzy', '#eaf1fa'), ('border', 'Obramowanie', '#bacade'),)),
    ('dark', 'Ciemne', (
        ('background', 'Tło', '#122c54'), ('text', 'Tekst', '#dde5ee'),
        ('heading', 'Nagłówek główny', '#edf5f7'), ('secondary_heading', 'Nagłówek drugorzędny', '#edf5f7'),
        ('overline', 'Nadtytuł', '#6afbfb'), ('button', 'Przycisk', '#9cfcfc'),
        ('button_text', 'Tekst przycisku', '#06101d'), ('link', 'Link', '#9cfcfc'),
        ('surface', 'Tło kart i formularzy', '#1c437d'), ('border', 'Obramowanie', '#42628a'),)),
)
DEFAULT_THEME = {f'{group}_{key}': default for group, _, fields in COLOR_GROUPS for key, _, default in fields}
DEFAULT_FOOTER = {
    'email': 'gdyniascienceslam@gmail.com', 'location': 'Gdynia',
    'additional': 'Konferencja Gdynia Science Slam jest organizowana przez <a href="https://lo3.gdynia.pl">III Liceum Ogólnokształcące z Oddziałami Dwujęzycznymi im. Marynarki Wojennej RP w Gdyni</a>',
}
HOME_FIELDS = (
    ('hero', 'Wprowadzenie', (
        ('hero_overline', 'Nadtytuł', 'Gdynia · Młodzi naukowcy · Wielkie idee'),
        ('hero_title', 'Tytuł', 'Gdynia Science Slam'),
        ('hero_date', 'Tekst przed ogłoszoną datą', 'Następne spotkanie nauki'),
        ('hero_no_date', 'Tekst bez daty', 'Data kolejnego wydarzenia wkrótce'),
        ('hero_status', 'Tekst pod odliczaniem', 'Do zobaczenia na żywo.'),
        ('hero_waiting', 'Tekst przed uruchomieniem odliczania', 'Odliczanie rozpocznie się po ogłoszeniu daty wydarzenia.'),
        ('hero_started', 'Tekst po rozpoczęciu wydarzenia', 'Wydarzenie już się rozpoczęło.'),
        ('days', 'Etykieta dni', 'dni'), ('hours', 'Etykieta godzin', 'godz.'),
        ('minutes', 'Etykieta minut', 'min'), ('seconds', 'Etykieta sekund', 'sek'),
        ('registration_link', 'Link rejestracji', 'Zgłoś się'), ('topics_link', 'Link wystąpień', 'Poznaj wystąpienia'),)),
    ('about', 'O nas', (
        ('about_overline', 'Nadtytuł', 'Nasza idea'), ('about_title', 'Tytuł', 'Nauka, która zostaje z Tobą.'),
        ('about_description', 'Opis', 'Gdynia Science Slam to konkurs popularyzujący naukę, w którym pasjonaci prezentują wybrane przez siebie tematy w przystępnej i kreatywnej formie.'),
        ('about_link', 'Link', 'Dowiedz się więcej'),)),
    ('team', 'Zespół', (
        ('team_overline', 'Nadtytuł', 'Ludzie za wydarzeniem'), ('team_title', 'Tytuł', 'Nasz zespół'),
        ('team_description', 'Opis', 'Zobacz, kto pracował nad tym wydarzeniem.'), ('team_link', 'Link', 'Poznaj cały zespół'),)),
    ('archive', 'Poprzednie edycje', (
        ('archive_overline', 'Nadtytuł', 'Wspomnienia i inspiracje'), ('archive_title', 'Tytuł', 'Każda edycja to nowa perspektywa.'),
        ('archive_description', 'Opis', 'Za nami już 3 edycje. Zobacz jak wyglądały.'), ('archive_link', 'Link', 'Przejdź do galerii'),)),
    ('partners', 'Partnerzy', (
        ('partners_overline', 'Nadtytuł', 'Razem dla nauki'), ('partners_title', 'Tytuł', 'Partnerzy'),
        ('partners_description', 'Opis', 'To dzięki nim pomysły młodych naukowców trafiają na scenę.'), ('partners_link', 'Link', 'Zobacz wszystkich partnerów'),)),
    ('join', 'Dołącz do nas (sekcja obecnie ukryta)', (
        ('join_title', 'Tytuł', 'Dołącz do nas'), ('join_contestant', 'Uczestnik', 'Uczestnik'),
        ('join_viewer', 'Widz', 'Widz'), ('join_volunteer', 'Wolontariusz', 'Wolontariusz'),)),
)
DEFAULT_HOME = {key: default for _, _, fields in HOME_FIELDS for key, _, default in fields}


def sanitize_html(value):
    soup = BeautifulSoup(value, 'html.parser')
    for node in soup.find_all(string=lambda text: isinstance(text, Comment)):
        node.extract()
    for tag in list(soup.find_all(True)):
        if tag.name in {'script', 'style', 'iframe', 'object', 'embed', 'svg', 'math', 'template'}:
            tag.decompose()
    for tag in list(soup.find_all(True)):
        if tag.name not in {'a', 'p', 'br', 'strong', 'b', 'em', 'i', 'span', 'ul', 'ol', 'li'}:
            tag.unwrap()
            continue
        href = tag.get('href', '') if tag.name == 'a' else ''
        tag.attrs.clear()
        if href and urlsplit(href.strip()).scheme.lower() in {'http', 'https', 'mailto', 'tel'}:
            tag['href'] = href.strip()
            tag['rel'] = 'noopener noreferrer'
    return str(soup)


def validate_settings(key, saved):
    defaults = {THEME_KEY: DEFAULT_THEME, FOOTER_KEY: DEFAULT_FOOTER, HOME_KEY: DEFAULT_HOME, PAGE_MODES_KEY: DEFAULT_PAGE_MODES}[key]
    if not isinstance(saved, dict) or set(saved) != set(defaults):
        raise ValueError('Nieprawidłowy zestaw ustawień.')
    if not all(isinstance(value, str) for value in saved.values()):
        raise ValueError('Wartości ustawień muszą być tekstem.')
    if key == PAGE_MODES_KEY:
        if any(value not in DISPLAY_MODES for value in saved.values()):
            raise ValueError('Wybierz domyślny, jasny lub ciemny tryb strony.')
        return saved
    if key == THEME_KEY:
        if not all(valid_color(value) for value in saved.values()):
            raise ValueError('Wybierz kolory w formacie #RRGGBB.')
        return {name: value.lower() for name, value in saved.items()}
    if any(len(value) > 10000 for value in saved.values()):
        raise ValueError('Pole może mieć maksymalnie 10000 znaków.')
    if key == FOOTER_KEY:
        return {name: sanitize_html(value) for name, value in saved.items()}
    return saved


def get_settings(db, key, defaults):
    setting = db.get(SystemSetting, key)
    try:
        saved = json.loads(setting.value) if setting else {}
        if not isinstance(saved, dict):
            saved = {}
        return validate_settings(key, {**defaults, **{name: value for name, value in saved.items() if name in defaults}})
    except (ValueError, TypeError):
        return defaults.copy()


def load_public_settings(db):
    return {
        'page_modes': get_settings(db, PAGE_MODES_KEY, DEFAULT_PAGE_MODES),
        'theme': get_settings(db, THEME_KEY, DEFAULT_THEME),
        'footer': get_settings(db, FOOTER_KEY, DEFAULT_FOOTER),
        'home': get_settings(db, HOME_KEY, DEFAULT_HOME),
    }

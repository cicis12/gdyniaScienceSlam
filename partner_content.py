"""Partner sections and logo validation shared by admin, public pages, and transfer."""
import re
from urllib.parse import urlsplit
from uuid import uuid4
import xml.etree.ElementTree as ET

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator
from models import SystemSetting
from image_uploads import MAX_IMAGE_BYTES, normalize_image

PARTNERS_KEY = 'partners_content'
MAX_SECTIONS = 50
MAX_PARTNERS = 200
LOGO_PATH_PATTERN = r'^/static/(?:assets/images|uploads)/[^\\\x00-\x1f]+\.(?:webp|png|jpg|jpeg|svg)$'


class Partner(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    id: str = Field(default_factory=lambda: uuid4().hex, pattern=r'^[a-z0-9_-]{1,64}$')
    name: str = Field(min_length=1, max_length=160)
    logo: str = Field(pattern=LOGO_PATH_PATTERN)
    website: str = Field(default='', max_length=1000)
    logo_scale: float = Field(default=1, ge=.5, le=3, allow_inf_nan=False)
    sort_order: int = Field(default=0, ge=0, le=100000)

    @field_validator('website')
    @classmethod
    def safe_website(cls, value):
        if value:
            url = urlsplit(value)
            if (url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password
                    or any(character.isspace() or ord(character) < 32 for character in value)):
                raise ValueError('Podaj poprawny adres strony HTTP lub HTTPS.')
        return value

    @field_validator('logo')
    @classmethod
    def safe_logo_path(cls, value):
        if any(part in {'.', '..'} for part in value.split('/')) or '?' in value or '#' in value:
            raise ValueError('Nieprawidłowa ścieżka logo.')
        return value


class PartnerSection(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    id: str = Field(default_factory=lambda: uuid4().hex, pattern=r'^[a-z0-9_-]{1,64}$')
    title: str = Field(min_length=1, max_length=160)
    highlighted: StrictBool = False
    enabled: StrictBool = True
    sort_order: int = Field(default=0, ge=0, le=100000)
    partners: list[Partner] = Field(default_factory=list, max_length=MAX_PARTNERS)


class PartnersConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: StrictBool = True
    sections: list[PartnerSection] = Field(default_factory=list, max_length=MAX_SECTIONS)

    @model_validator(mode='after')
    def unique_ids_and_limits(self):
        ids = [partner.id for section in self.sections for partner in section.partners]
        if len(ids) > MAX_PARTNERS or len(ids) != len(set(ids)) or len({s.id for s in self.sections}) != len(self.sections):
            raise ValueError('Zbyt wielu partnerów lub powtórzone identyfikatory.')
        return self

    @property
    def visible_sections(self):
        return [section for section in self.sections if self.enabled and section.enabled and section.partners]

    @property
    def carousel_partners(self):
        return [partner for section in self.visible_sections for partner in section.partners]


def default_partner(id, name, filename, sort_order=0, scale=1):
    return dict(id=id, name=name, logo='/static/assets/images/partners/' + filename,
                sort_order=sort_order, logo_scale=scale)


DEFAULT_PARTNERS = dict(enabled=True, sections=[
    dict(id='sponsor-glowny', title='Sponsor główny', highlighted=True, sort_order=0, partners=[
        default_partner('izopanel', 'Izopanel', 'izopanel.png')]),
    dict(id='sponsorzy', title='Sponsorzy', sort_order=1, partners=[
        default_partner('helion', 'Helion', 'helion.png', 0),
        default_partner('milomi', 'MIŁO.MI', 'milomi.png', 1),
        default_partner('muzeum', 'Muzeum Emigracji w Gdyni', 'muzeumemigracji.png', 2)]),
    dict(id='partnerzy', title='Partnerzy', sort_order=2, partners=[
        default_partner('talent', 'Stowarzyszenie Talent', 'talent.jpg')]),
    dict(id='media', title='Patroni medialni', sort_order=3, partners=[
        default_partner('radio', 'Radio Gdańsk', 'RG logo.svg', 0, 2),
        default_partner('trojmiasto', 'trojmiasto.pl', 'trojmiastopl.jpg', 1)]),
    dict(id='jury', title='Jury', sort_order=4, partners=[
        default_partner('iopan', 'IO PAN', 'iopan.svg')]),
    dict(id='organizator', title='Organizator', sort_order=5, partners=[
        default_partner('lo3', 'III Liceum Ogólnokształcące w Gdyni', '3lo.png')]),
])


def get_partners(db):
    setting = db.get(SystemSetting, PARTNERS_KEY)
    config = PartnersConfig.model_validate_json(setting.value) if setting else PartnersConfig.model_validate(DEFAULT_PARTNERS)
    config.sections.sort(key=lambda section: section.sort_order)
    for section in config.sections:
        section.partners.sort(key=lambda partner: partner.sort_order)
    return config


def save_partners(db, config):
    validated = PartnersConfig.model_validate(config.model_dump())
    db.merge(SystemSetting(key=PARTNERS_KEY, value=validated.model_dump_json()))


SVG_NS = 'http://www.w3.org/2000/svg'
SVG_TAGS = {'svg', 'g', 'path', 'rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon', 'defs',
            'clipPath', 'linearGradient', 'radialGradient', 'stop', 'mask', 'pattern', 'use',
            'text', 'tspan', 'title', 'desc'}
SVG_ATTRS = {'id', 'viewBox', 'width', 'height', 'preserveAspectRatio', 'x', 'y', 'x1', 'y1', 'x2', 'y2',
             'cx', 'cy', 'r', 'rx', 'ry', 'd', 'points', 'transform', 'fill', 'fill-opacity', 'fill-rule',
             'stroke', 'stroke-width', 'stroke-linecap', 'stroke-linejoin', 'stroke-opacity',
             'stroke-dasharray', 'stroke-dashoffset', 'stroke-miterlimit', 'opacity', 'clip-path',
             'clip-rule', 'clipPathUnits', 'mask', 'maskUnits', 'maskContentUnits', 'gradientUnits',
             'gradientTransform', 'spreadMethod', 'offset', 'stop-color', 'stop-opacity',
             'patternUnits', 'patternContentUnits', 'patternTransform', 'font-family', 'font-size',
             'font-weight', 'font-style', 'letter-spacing', 'text-anchor', 'dominant-baseline',
             'display', 'visibility'}


def safe_svg_value(value):
    if any(character in value for character in ('\\', '<', '>', '@', '{', '}')) or 'expression' in value.lower():
        raise ValueError('Niedozwolona wartość w SVG.')
    if 'url' in value.lower() and not re.fullmatch(r'url\(\s*#[a-zA-Z0-9_:-]+\s*\)', value):
        raise ValueError('SVG nie może odwoływać się do zewnętrznych zasobów.')
    return value


def normalize_svg(data):
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError('Logo może mieć maksymalnie 10 MB.')
    try:
        source = data.decode('utf-8-sig')
        # Strip an external SVG DTD declaration without resolving it. Internal entities remain forbidden.
        source = re.sub(r'<!DOCTYPE\s+svg\s+(?:PUBLIC|SYSTEM)\s+[^\[>]+>', '', source, flags=re.I)
        if '<!doctype' in source.lower() or '<!entity' in source.lower():
            raise ValueError('Niedozwolona deklaracja w SVG.')
        root = ET.fromstring(source)
    except (UnicodeDecodeError, ET.ParseError):
        raise ValueError('Wybierz poprawny plik SVG.') from None
    if root.tag.split('}')[-1] != 'svg' or sum(1 for _ in root.iter()) > 20000:
        raise ValueError('Nieprawidłowe lub zbyt złożone SVG.')
    if any(node.tag.split('}')[-1] in {'script', 'foreignObject', 'image', 'style', 'animate', 'set'} for node in root.iter()):
        raise ValueError('SVG musi zawierać wyłącznie statyczną grafikę wektorową.')

    def clean(node, depth=0):
        if depth > 64:
            raise ValueError('Zbyt złożone SVG.')
        tag = node.tag.split('}')[-1]
        if tag not in SVG_TAGS:
            return None
        result = ET.Element('{' + SVG_NS + '}' + tag)
        if tag in {'text', 'tspan', 'title', 'desc'}:
            result.text = node.text
        for key, value in node.attrib.items():
            if key.startswith('{'):
                if key == '{http://www.w3.org/1999/xlink}href' and tag == 'use':
                    key = 'href'
                else:
                    continue
            if key == 'href' and tag == 'use':
                if not re.fullmatch(r'#[a-zA-Z0-9_:-]+', value):
                    raise ValueError('Niedozwolone odwołanie w SVG.')
                result.set(key, value)
            elif key == 'style':
                for declaration in value.split(';'):
                    if not declaration.strip():
                        continue
                    if ':' not in declaration:
                        raise ValueError('Nieprawidłowy styl SVG.')
                    property, content = (part.strip() for part in declaration.split(':', 1))
                    if property in SVG_ATTRS - {'id', 'viewBox'}:
                        result.set(property, safe_svg_value(content))
            elif key in SVG_ATTRS:
                result.set(key, safe_svg_value(value))
        for child in node:
            converted = clean(child, depth + 1)
            if converted is not None:
                converted.tail = child.tail
                result.append(converted)
        return result

    ET.register_namespace('', SVG_NS)
    output = clean(root)
    return ET.tostring(output, encoding='utf-8', xml_declaration=True)


def normalize_logo(data, filename='logo.webp'):
    if filename.lower().endswith('.svg'):
        return normalize_svg(data), 'svg'
    return normalize_image(data, max_size=1600), 'webp'

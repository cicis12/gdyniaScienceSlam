"""Portable public content bundles, excluding accounts and visitor data."""
from datetime import datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Literal
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED, BadZipFile
import json
import re
import shutil
import stat
import zlib
import xml.etree.ElementTree as ET

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator
from sqlalchemy import func

from forms import FormDefinition
from about_content import TimelineEntry, MAX_ENTRIES, get_timeline, save_timeline
from gallery import FeaturedVideo, VIDEO_KEY, get_featured_video
from image_uploads import MAX_IMAGE_BYTES, normalize_image
from models import FormInfo, FormVersion, GalleryPhoto, SystemSetting, TeamMember
from site_pages import PUBLIC_PAGES, page_visibility
from system_settings import THEME_KEY, FOOTER_KEY, HOME_KEY, PAGE_MODES_KEY, load_public_settings, validate_settings
from partner_content import (Partner, PartnerSection, PartnersConfig, MAX_PARTNERS,
                             get_partners, save_partners, normalize_svg)
import document_content
from document_content import Document, MAX_DOCUMENTS, MAX_PDF_BYTES, get_documents, save_documents, document_path, validate_pdf
from home_images import HomeImage, HomeImages, get_home_images, save_home_images
from team_theme import DEFAULT_PALETTE, PALETTE_KEY, DETAILS_KEY, get_team_palette, team_details_enabled, valid_color

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / 'static'
IMPORT_DIR = STATIC_DIR / 'uploads/imports'
MAX_ARCHIVE_BYTES = 150 * 1024 * 1024
MEDIA_PATTERN = r'media/[a-f0-9]{64}\.(?:webp|png|jpg)'
LOGO_MEDIA_PATTERN = r'media/[a-f0-9]{64}\.(?:webp|png|jpg|svg)'
DOCUMENT_MEDIA_PATTERN = r'documents/[a-f0-9]{64}\.pdf'
ADDITIONAL_SETTING_KEYS = {THEME_KEY, FOOTER_KEY, HOME_KEY, PAGE_MODES_KEY}
OPTIONAL_SETTING_KEYS = {'event_date_only'}
SETTING_KEYS = {PALETTE_KEY, DETAILS_KEY, 'event_datetime', 'voting_enabled'} | {'page_visible:' + key for key, _, _ in PUBLIC_PAGES}


class Record(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class TeamRecord(Record):
    name: str = Field(min_length=1, max_length=160)
    position: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=10000)
    photo: str = Field(pattern='^' + MEDIA_PATTERN + '$')


class PhotoRecord(Record):
    year: int = Field(ge=2000, le=2100)
    caption: str = Field(max_length=300)
    sort_order: int = Field(ge=0, le=100000)
    photo: str = Field(pattern='^' + MEDIA_PATTERN + '$')


class TimelineRecord(TimelineEntry):
    photo: str = Field(pattern='^' + MEDIA_PATTERN + '$')


def check_svg(svg):
    if not svg:
        return
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        raise ValueError('Nieprawidłowa ikona SVG formularza.') from None
    tags = {'svg', 'g', 'path', 'circle', 'ellipse', 'rect', 'line', 'polyline', 'polygon', 'title', 'desc'}
    attrs = {'class', 'viewBox', 'width', 'height', 'fill', 'fill-rule', 'clip-rule', 'stroke', 'stroke-width', 'stroke-linecap', 'stroke-linejoin', 'stroke-dasharray', 'stroke-dashoffset', 'stroke-miterlimit', 'opacity', 'fill-opacity', 'stroke-opacity', 'd', 'cx', 'cy', 'r', 'rx', 'ry', 'x', 'y', 'x1', 'x2', 'y1', 'y2', 'points', 'transform', 'aria-hidden', 'role', 'focusable'}
    for node in root.iter():
        if node.tag.split('}')[-1] not in tags:
            raise ValueError('Niedozwolony element w ikonie SVG.')
        for key, value in node.attrib.items():
            if key not in attrs or 'url(' in value.lower():
                raise ValueError('Niedozwolony atrybut w ikonie SVG.')


class FormRecord(Record):
    slug: str = Field(min_length=1, max_length=160, pattern=r'^[a-zA-Z0-9_-]+$')
    name: str = Field(min_length=1, max_length=160)
    enabled: StrictBool
    display_name: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=10000)
    definition: FormDefinition

    @field_validator('definition')
    @classmethod
    def safe_definition(cls, value):
        if len(value.fields) > 200:
            raise ValueError('Za dużo pól formularza.')
        for field in value.fields:
            check_svg(field.svg)
        return value


class PartnerRecord(Partner):
    logo: str = Field(pattern='^' + LOGO_MEDIA_PATTERN + '$')


class PartnerSectionRecord(PartnerSection):
    partners: list[PartnerRecord] = Field(default_factory=list, max_length=MAX_PARTNERS)


class PartnersBundle(PartnersConfig):
    sections: list[PartnerSectionRecord] = Field(default_factory=list, max_length=50)


class DocumentRecord(Document):
    file: str = Field(pattern='^' + DOCUMENT_MEDIA_PATTERN + '$')

    @field_validator('file')
    @classmethod
    def valid_file(cls, value):
        return value


class HomeImageRecord(HomeImage):
    photo: str = Field(pattern='^' + MEDIA_PATTERN + '$')


class HomeImagesBundle(BaseModel):
    model_config = ConfigDict(extra='forbid')
    hero: HomeImageRecord
    about: HomeImageRecord
    archive: HomeImageRecord


class SiteBundle(Record):
    format: Literal['gdynia-science-slam']
    version: Literal[1, 2, 3, 4]
    documents: list[DocumentRecord] | None = Field(default=None, max_length=MAX_DOCUMENTS)
    home_images: HomeImagesBundle | None = None
    partners: PartnersBundle | None = None
    about: list[TimelineRecord] | None = Field(default=None, max_length=MAX_ENTRIES)
    settings: dict[str, str]
    team: list[TeamRecord] = Field(max_length=200)
    gallery: list[PhotoRecord] = Field(max_length=1000)
    video: FeaturedVideo
    forms: list[FormRecord] = Field(max_length=100)
    registration_forms: list[str] = Field(max_length=3)

    @model_validator(mode='after')
    def check_config(self):
        if (self.version >= 2 and self.about is None) or (self.version == 1 and self.about is not None):
            raise ValueError('Nieprawidłowa oś czasu dla tej wersji pakietu.')
        if (self.version >= 3 and self.partners is None) or (self.version < 3 and self.partners is not None):
            raise ValueError('Nieprawidłowa konfiguracja partnerów dla tej wersji pakietu.')
        if (self.version == 4 and (self.documents is None or self.home_images is None)) or (self.version < 4 and (self.documents is not None or self.home_images is not None)):
            raise ValueError('Nieprawidłowe dokumenty lub zdjęcia strony głównej dla tej wersji pakietu.')
        if self.documents is not None and len({item.id for item in self.documents}) != len(self.documents):
            raise ValueError('Powtórzone identyfikatory dokumentów.')
        if self.about is not None and len({entry.id for entry in self.about}) != len(self.about):
            raise ValueError('Powtórzone identyfikatory etapów osi czasu.')
        if not SETTING_KEYS <= set(self.settings) or set(self.settings) - (SETTING_KEYS | ADDITIONAL_SETTING_KEYS | OPTIONAL_SETTING_KEYS):
            raise ValueError('Nieobsługiwany zestaw ustawień.')
        for key, value in self.settings.items():
            if key.startswith('page_visible:') or key in {DETAILS_KEY, 'voting_enabled', 'event_date_only'}:
                if value not in {'true', 'false'}:
                    raise ValueError('Nieprawidłowa widoczność strony.')
            elif key == 'event_datetime' and value:
                datetime.fromisoformat(value)
            elif key in ADDITIONAL_SETTING_KEYS:
                self.settings[key] = json.dumps(validate_settings(key, json.loads(value)), ensure_ascii=False)
            elif key == PALETTE_KEY:
                palette = json.loads(value)
                if not isinstance(palette, dict) or set(palette) != set(DEFAULT_PALETTE) or not all(valid_color(color) for color in palette.values()):
                    raise ValueError('Nieprawidłowa paleta kolorów.')
        slugs = [form.slug for form in self.forms]
        if len(set(slugs)) != len(slugs) or len({form.name for form in self.forms}) != len(self.forms):
            raise ValueError('Powtórzone formularze.')
        enabled_slugs = {form.slug for form in self.forms if form.enabled}
        if len(set(self.registration_forms)) != len(self.registration_forms) or not set(self.registration_forms) <= enabled_slugs:
            raise ValueError('Nieprawidłowy wybór formularzy rejestracji.')
        return self


def export_bundle(db):
    media = {}

    def add_media(url):
        if not url.startswith(('/static/assets/images/', '/static/uploads/')):
            raise ValueError('Zdjęcie nie znajduje się w publicznym katalogu witryny.')
        path = (STATIC_DIR / url.removeprefix('/static/')).resolve()
        if not path.is_relative_to(STATIC_DIR.resolve()) or path.suffix.lower() not in {'.webp', '.png', '.jpg', '.jpeg'}:
            raise ValueError('Nieprawidłowa ścieżka zdjęcia.')
        if not path.is_file() or path.stat().st_size > MAX_IMAGE_BYTES:
            raise ValueError('Brakuje zdjęcia lub plik jest zbyt duży.')
        data = path.read_bytes()
        extension = 'jpg' if path.suffix.lower() == '.jpeg' else path.suffix.lower()[1:]
        name = f'media/{sha256(data).hexdigest()}.{extension}'
        media[name] = data
        if sum(map(len, media.values())) > MAX_ARCHIVE_BYTES:
            raise ValueError('Pakiet przekracza limit 150 MB.')
        return name

    def add_logo(url):
        if not url.startswith(('/static/assets/images/', '/static/uploads/')):
            raise ValueError('Logo nie znajduje się w katalogu witryny.')
        path = (STATIC_DIR / url.removeprefix('/static/')).resolve()
        if not path.is_relative_to(STATIC_DIR.resolve()) or path.suffix.lower() not in {'.svg', '.png', '.webp', '.jpg', '.jpeg'}:
            raise ValueError('Nieprawidłowa ścieżka logo.')
        if not path.is_file() or path.stat().st_size > MAX_IMAGE_BYTES:
            raise ValueError('Brakuje logo lub plik jest zbyt duży.')
        raw = path.read_bytes()
        data = normalize_svg(raw) if path.suffix.lower() == '.svg' else raw
        extension = 'jpg' if path.suffix.lower() == '.jpeg' else path.suffix.lower()[1:]
        name = f'media/{sha256(data).hexdigest()}.{extension}'
        media[name] = data
        if sum(map(len, media.values())) > MAX_ARCHIVE_BYTES:
            raise ValueError('Pakiet przekracza limit 150 MB.')
        return name

    settings = {key: value for key, value in db.query(SystemSetting.key, SystemSetting.value).all() if key in SETTING_KEYS | ADDITIONAL_SETTING_KEYS | OPTIONAL_SETTING_KEYS}
    settings = {'event_datetime': '', 'voting_enabled': 'true', **settings}
    public = load_public_settings(db)
    settings.update({key: json.dumps(public[section], ensure_ascii=False)
                     for key, section in ((THEME_KEY, 'theme'), (FOOTER_KEY, 'footer'), (HOME_KEY, 'home'), (PAGE_MODES_KEY, 'page_modes'))})
    settings[PALETTE_KEY] = json.dumps(get_team_palette(db))
    settings[DETAILS_KEY] = 'true' if team_details_enabled(db) else 'false'
    settings.update({'page_visible:' + key: 'true' if visible else 'false' for key, visible in page_visibility(db).items()})
    team = [dict(name=m.name, position=m.position, description=m.description, photo=add_media(m.photo))
            for m in db.query(TeamMember).order_by(TeamMember.id)]
    gallery = [dict(year=p.year, caption=p.caption, sort_order=p.sort_order, photo=add_media(p.photo))
               for p in db.query(GalleryPhoto).order_by(GalleryPhoto.year.desc(), GalleryPhoto.sort_order, GalleryPhoto.id)]
    about = [{**entry.model_dump(), 'photo': add_media(entry.photo)} for entry in get_timeline(db)]
    partners = get_partners(db).model_dump()
    for section in partners['sections']:
        for partner in section['partners']:
            partner['logo'] = add_logo(partner['logo'])
    home_images = get_home_images(db).model_dump()
    for image in home_images.values():
        image['photo'] = add_media(image['photo'])
    documents = []
    for document in get_documents(db):
        path = document_path(document)
        if not path.is_file() or path.stat().st_size > MAX_PDF_BYTES:
            raise ValueError('Brakuje dokumentu lub plik jest zbyt duży.')
        data = validate_pdf(path.read_bytes())
        name = f'documents/{sha256(data).hexdigest()}.pdf'
        media[name] = data
        if sum(map(len, media.values())) > MAX_ARCHIVE_BYTES:
            raise ValueError('Pakiet przekracza limit 150 MB.')
        documents.append({**document.model_dump(), 'file': name})
    forms, id_to_slug = [], {}
    for form in db.query(FormInfo).order_by(FormInfo.id):
        version = db.get(FormVersion, form.cur_version_id)
        if not version or version.form_id != form.id:
            raise ValueError(f'Formularz {form.name} nie ma aktywnej wersji.')
        forms.append(dict(slug=form.slug, name=form.name, enabled=form.enabled, display_name=version.display_name,
                          description=version.description, definition=version.definition))
        if form.enabled:
            id_to_slug[form.id] = form.slug
    selected = db.get(SystemSetting, 'registration_form_ids')
    selected_ids = [int(value) for value in (selected.value if selected else '').split(',') if value]
    bundle = SiteBundle(format='gdynia-science-slam', version=4, documents=documents, home_images=home_images, partners=partners, about=about, settings=settings, team=team, gallery=gallery,
                        video=get_featured_video(db), forms=forms,
                        registration_forms=list(dict.fromkeys(id_to_slug[value] for value in selected_ids if value in id_to_slug))[:3])
    output = BytesIO()
    with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json', bundle.model_dump_json(indent=2))
        for name, data in media.items():
            archive.writestr(name, data)
    if len(output.getbuffer()) > MAX_ARCHIVE_BYTES:
        raise ValueError('Pakiet przekracza limit 150 MB.')
    return output.getvalue()


def inspect_bundle(data):
    """Validate every entry without extracting archive-provided paths."""
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ValueError('Pakiet może mieć maksymalnie 150 MB.')
    try:
        with ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(entries) > 1554 or len(names) != len(set(names)) or names.count('manifest.json') != 1:
                raise ValueError('Nieprawidłowa struktura pakietu.')
            if sum(entry.file_size for entry in entries) > MAX_ARCHIVE_BYTES:
                raise ValueError('Rozpakowany pakiet przekracza 150 MB.')
            for entry in entries:
                limit = (5 * 1024 * 1024 if entry.filename == 'manifest.json' else
                         MAX_PDF_BYTES if re.fullmatch(DOCUMENT_MEDIA_PATTERN, entry.filename) else MAX_IMAGE_BYTES)
                if entry.file_size > limit or entry.flag_bits & 1 or stat.S_ISLNK(entry.external_attr >> 16):
                    raise ValueError('Niedozwolony lub zbyt duży plik w pakiecie.')
                if entry.filename != 'manifest.json' and not (re.fullmatch(LOGO_MEDIA_PATTERN, entry.filename) or re.fullmatch(DOCUMENT_MEDIA_PATTERN, entry.filename)):
                    raise ValueError('Niedozwolona ścieżka w pakiecie.')
            bundle = SiteBundle.model_validate_json(archive.read('manifest.json'))
            references = {record.photo for record in [*bundle.team, *bundle.gallery, *(bundle.about or [])]}
            if bundle.partners is not None:
                references.update(partner.logo for section in bundle.partners.sections for partner in section.partners)
            if bundle.home_images is not None:
                references.update(image['photo'] for image in bundle.home_images.model_dump().values())
            if bundle.documents is not None:
                references.update(document.file for document in bundle.documents)
            if references != set(names) - {'manifest.json'}:
                raise ValueError('Brakuje zdjęć lub pakiet zawiera nieużywane pliki.')
            media = {}
            normalized_size = 0
            for name in references:
                raw = archive.read(name)
                if sha256(raw).hexdigest() != Path(name).stem:
                    raise ValueError('Suma kontrolna zdjęcia jest nieprawidłowa.')
                media[name] = (validate_pdf(raw) if name.endswith('.pdf') else
                               normalize_svg(raw) if name.endswith('.svg') else normalize_image(raw))
                normalized_size += len(media[name])
                if normalized_size > MAX_ARCHIVE_BYTES:
                    raise ValueError('Zdjęcia w pakiecie przekraczają 150 MB po przetworzeniu.')
            return bundle, media
    except (BadZipFile, KeyError, RuntimeError, OSError, NotImplementedError, EOFError, zlib.error):
        raise ValueError('Nie można odczytać pakietu ZIP.') from None


def check_form_conflicts(db, bundle):
    for record in bundle.forms:
        other = db.query(FormInfo).filter(FormInfo.name == record.name, FormInfo.slug != record.slug).first()
        if other:
            raise ValueError(f'Nazwa formularza „{record.name}” jest już używana pod adresem /forms/{other.slug}. Zmień nazwę przed importem.')


def apply_bundle(db, bundle, media, scope):
    if scope not in {'gallery', 'all'}:
        raise ValueError('Nieprawidłowy zakres importu.')
    if scope == 'all':
        check_form_conflicts(db, bundle)
    records = [*bundle.gallery, *(bundle.team if scope == 'all' else []), *((bundle.about or []) if scope == 'all' else [])]
    partner_records = [partner for section in bundle.partners.sections for partner in section.partners] if scope == 'all' and bundle.partners is not None else []
    home_records = list(bundle.home_images.model_dump().values()) if scope == 'all' and bundle.home_images is not None else []
    destination = IMPORT_DIR / uuid4().hex
    new_documents = []
    paths = {}
    try:
        if records or partner_records or home_records:
            destination.mkdir(parents=True)
        for name in {record.photo for record in records} | {record.logo for record in partner_records} | {record['photo'] for record in home_records}:
            filename = Path(name).stem + ('.svg' if name.endswith('.svg') else '.webp')
            (destination / filename).write_bytes(media[name])
            paths[name] = f'/static/uploads/imports/{destination.name}/{filename}'
        db.query(GalleryPhoto).delete(synchronize_session='fetch')
        db.add_all([GalleryPhoto(**{**record.model_dump(), 'photo': paths[record.photo]}) for record in bundle.gallery])
        db.merge(SystemSetting(key=VIDEO_KEY, value=bundle.video.model_dump_json()))
        if scope == 'all':
            if bundle.home_images is not None:
                home = bundle.home_images.model_dump()
                for image in home.values():
                    image['photo'] = paths[image['photo']]
                save_home_images(db, HomeImages.model_validate(home))
            if bundle.documents is not None:
                imported_documents = []
                document_paths = {}
                if bundle.documents:
                    document_content.DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
                for document in bundle.documents:
                    if document.file not in document_paths:
                        path = document_content.DOCUMENTS_DIR / (uuid4().hex + '.pdf')
                        new_documents.append(path)
                        path.write_bytes(media[document.file])
                        document_paths[document.file] = 'uploads/documents/' + path.name
                    imported_documents.append(Document(**{**document.model_dump(), 'file': document_paths[document.file]}))
                save_documents(db, imported_documents)
            if bundle.partners is not None:
                config = bundle.partners.model_dump()
                for section in config['sections']:
                    for partner in section['partners']:
                        partner['logo'] = paths[partner['logo']]
                save_partners(db, PartnersConfig.model_validate(config))
            if bundle.about is not None:
                save_timeline(db, [TimelineEntry(**{**entry.model_dump(), 'photo': paths[entry.photo]}) for entry in bundle.about])
            db.query(TeamMember).delete(synchronize_session='fetch')
            db.add_all([TeamMember(**{**record.model_dump(), 'photo': paths[record.photo]}) for record in bundle.team])
            for key, value in bundle.settings.items():
                db.merge(SystemSetting(key=key, value=value))
            imported_ids = {}
            for record in bundle.forms:
                form = db.query(FormInfo).filter_by(slug=record.slug).first()
                if form is None:
                    form = FormInfo(slug=record.slug, name=record.name, enabled=record.enabled, cur_version_id=0)
                    db.add(form)
                    db.flush()
                form.name, form.enabled = record.name, record.enabled
                current = db.get(FormVersion, form.cur_version_id)
                definition = record.definition.model_dump(mode='json')
                if not current or (current.display_name, current.description, current.definition) != (record.display_name, record.description, definition):
                    number = (db.query(func.max(FormVersion.version_num)).filter(FormVersion.form_id == form.id).scalar() or 0) + 1
                    version = FormVersion(form_id=form.id, version_num=number, display_name=record.display_name,
                                          description=record.description, definition=definition)
                    db.add(version)
                    db.flush()
                    form.cur_version_id = version.id
                imported_ids[record.slug] = form.id
            db.merge(SystemSetting(key='registration_form_ids', value=','.join(str(imported_ids[slug]) for slug in bundle.registration_forms)))
        db.commit()
    except Exception:
        db.rollback()
        for path in new_documents:
            path.unlink(missing_ok=True)
        if destination.exists():
            shutil.rmtree(destination)
        raise

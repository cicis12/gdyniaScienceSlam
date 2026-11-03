"""Ordered, validated sections for the partner invitation page."""
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, EmailStr, Field, TypeAdapter, field_validator, model_validator
from form_icons import check_svg
from models import SystemSetting

PARTNERSHIP_KEY = 'become_partner_content'
PHOTO_PATTERN = r'^/static/(?:assets/images|uploads)/[a-zA-Z0-9_./-]+\.(?:webp|png|jpg|jpeg)$'
SECTION_TYPES = {'grid': 'Siatka 6 tekstów', 'paragraph': 'Akapit', 'icons': '3 kolumny z ikonami SVG',
                 'heading': 'Duży nagłówek', 'person': 'Osoby kontaktowe', 'faq': 'FAQ', 'contact': 'Formularz kontaktowy'}


class ContentModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class TextItem(ContentModel):
    title: str = Field(default='', max_length=160)
    text: str = Field(default='', max_length=10000)


class IconItem(TextItem):
    svg: str = Field(default='', max_length=20000)

    @field_validator('svg')
    @classmethod
    def valid_svg(cls, value):
        check_svg(value)
        return value


class Question(ContentModel):
    question: str = Field(min_length=1, max_length=300)
    answer: str = Field(min_length=1, max_length=10000)


class Section(ContentModel):
    id: str = Field(default_factory=lambda: uuid4().hex, pattern=r'^[a-z0-9_-]{1,64}$')
    title: str = Field(default='', max_length=300)
    enabled: bool = False
    sort_order: int = Field(default=0, ge=0, le=100000)


class GridSection(Section):
    type: Literal['grid'] = 'grid'
    items: list[TextItem] = Field(default_factory=lambda: [TextItem() for _ in range(6)], min_length=6, max_length=6)


class ParagraphSection(Section):
    type: Literal['paragraph'] = 'paragraph'
    text: str = Field(default='', max_length=10000)


class IconsSection(Section):
    type: Literal['icons'] = 'icons'
    items: list[IconItem] = Field(default_factory=lambda: [IconItem() for _ in range(3)], min_length=3, max_length=3)


class HeadingSection(Section):
    type: Literal['heading'] = 'heading'


class ContactPerson(ContentModel):
    id: str = Field(default_factory=lambda: uuid4().hex, pattern=r'^[a-z0-9_-]{1,64}$')
    name: str = Field(default='', max_length=160)
    occupation: str = Field(default='', max_length=160)
    details: str = Field(default='', max_length=10000)
    photo: str = Field(default='', max_length=500)

    @field_validator('photo')
    @classmethod
    def valid_photo(cls, value):
        import re
        if value and not re.fullmatch(PHOTO_PATTERN, value):
            raise ValueError('Nieprawidłowa ścieżka zdjęcia.')
        return value


class PersonSection(Section):
    type: Literal['person'] = 'person'
    people: list[ContactPerson] = Field(default_factory=lambda: [ContactPerson()], max_length=20)
    team_link: bool = False
    team_link_label: str = Field(default='Poznaj cały zespół', min_length=1, max_length=160)

    @model_validator(mode='before')
    @classmethod
    def migrate_single_person(cls, value):
        if isinstance(value, dict) and any(key in value for key in ('name', 'occupation', 'details', 'photo')):
            value = dict(value)
            person = {key: value.pop(key, '') for key in ('name', 'occupation', 'details', 'photo')}
            value.setdefault('people', [{'id': 'contact', **person}])
        return value

    @model_validator(mode='after')
    def unique_people(self):
        if len({person.id for person in self.people}) != len(self.people):
            raise ValueError('Powtórzone identyfikatory osób.')
        return self


class FAQSection(Section):
    type: Literal['faq'] = 'faq'
    items: list[Question] = Field(default_factory=list, max_length=50)


class ContactSection(Section):
    type: Literal['contact'] = 'contact'
    text: str = Field(default='', max_length=10000)


PageSection = Annotated[GridSection | ParagraphSection | IconsSection | HeadingSection | PersonSection | FAQSection | ContactSection,
                        Field(discriminator='type')]
SECTION_ADAPTER = TypeAdapter(PageSection)


class PartnershipConfig(ContentModel):
    title: str = Field(default='Zostań partnerem', min_length=1, max_length=160)
    featured: bool = False
    uuid_only: bool = False
    teaser: str = Field(default='Wspólnie stwórzmy kolejną edycję Gdynia Science Slam.', max_length=1000)
    link_label: str = Field(default='Zostań partnerem', min_length=1, max_length=160)
    feature_photo: str = Field(default='', max_length=500)
    recipient: str = Field(default='', max_length=254)
    sections: list[PageSection] = Field(default_factory=list, max_length=50)

    @field_validator('feature_photo')
    @classmethod
    def valid_feature_photo(cls, value):
        return ContactPerson.valid_photo(value)

    @field_validator('recipient')
    @classmethod
    def valid_recipient(cls, value):
        return str(TypeAdapter(EmailStr).validate_python(value)) if value else ''

    @model_validator(mode='after')
    def unique_sections(self):
        if len({section.id for section in self.sections}) != len(self.sections):
            raise ValueError('Powtórzone identyfikatory sekcji.')
        return self


def get_partnership(db):
    setting = db.get(SystemSetting, PARTNERSHIP_KEY)
    config = PartnershipConfig.model_validate_json(setting.value) if setting else PartnershipConfig()
    config.sections.sort(key=lambda section: section.sort_order)
    return config


def save_partnership(db, config):
    config = PartnershipConfig.model_validate(config.model_dump())
    db.merge(SystemSetting(key=PARTNERSHIP_KEY, value=config.model_dump_json()))


def new_section(kind, sort_order):
    return SECTION_ADAPTER.validate_python({'type': kind, 'title': SECTION_TYPES[kind], 'sort_order': sort_order})

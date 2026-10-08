"""Editable homepage photos, separate from copy and dynamic carousels."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from models import SystemSetting

HOME_IMAGES_KEY = 'home_images'
IMAGE_SLOTS = (('hero', 'Hero · zdjęcie w tle'), ('about', 'O nas · zdjęcie'), ('archive', 'Poprzednie edycje · zdjęcie'))
IMAGE_POSITIONS = (('center', 'Środek'), ('top', 'Góra'), ('bottom', 'Dół'), ('left', 'Lewa strona'), ('right', 'Prawa strona'))


class HomeImage(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    photo: str = Field(pattern=r'^/static/(?:assets/images|uploads)/[a-zA-Z0-9_./-]+\.(?:webp|png|jpg|jpeg)$')
    alt: str = Field(default='', max_length=300)
    position: Literal['center', 'top', 'bottom', 'left', 'right'] = 'center'

    @field_validator('photo')
    @classmethod
    def safe_path(cls, value):
        if any(part in {'.', '..'} for part in value.split('/')):
            raise ValueError('Nieprawidłowa ścieżka zdjęcia.')
        return value


class HomeImages(BaseModel):
    model_config = ConfigDict(extra='forbid')
    hero: HomeImage = HomeImage(photo='/static/assets/images/hero.webp')
    about: HomeImage = HomeImage(photo='/static/assets/images/gallery6.webp')
    archive: HomeImage = HomeImage(photo='/static/assets/images/gallery5.webp')


def get_home_images(db):
    setting = db.get(SystemSetting, HOME_IMAGES_KEY)
    return HomeImages.model_validate_json(setting.value) if setting else HomeImages()


def save_home_images(db, images):
    db.merge(SystemSetting(key=HOME_IMAGES_KEY, value=HomeImages.model_validate(images.model_dump()).model_dump_json()))

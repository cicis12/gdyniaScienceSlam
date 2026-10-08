"""Gallery metadata and supported video links."""
import re
from urllib.parse import urlparse, parse_qs

from pydantic import BaseModel, ConfigDict, Field, model_validator
from models import SystemSetting

VIDEO_KEY = 'gallery_featured_video'


def video_embed_url(url):
    if not url:
        return ''
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Użyj linku HTTPS do filmu YouTube lub Vimeo.')
    host = parsed.hostname
    parts = parsed.path.strip('/').split('/')
    video_id = ''
    if host == 'youtu.be' and len(parts) == 1:
        video_id = parts[0]
    elif host in {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'www.youtube-nocookie.com'}:
        if parsed.path == '/watch':
            video_id = parse_qs(parsed.query).get('v', [''])[0]
        elif len(parts) == 2 and parts[0] in {'embed', 'shorts'}:
            video_id = parts[1]
    if video_id and re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
        return f'https://www.youtube-nocookie.com/embed/{video_id}'
    if host in {'vimeo.com', 'www.vimeo.com', 'player.vimeo.com'}:
        match = re.fullmatch(r'/(?:video/)?([0-9]+)(?:/([a-fA-F0-9]+))?/?', parsed.path)
        if match:
            private_hash = match[2] or parse_qs(parsed.query).get('h', [''])[0]
            if private_hash and not re.fullmatch(r'[a-fA-F0-9]{1,64}', private_hash):
                raise ValueError('Nieprawidłowy link Vimeo.')
            return f'https://player.vimeo.com/video/{match[1]}' + (f'?h={private_hash}' if private_hash else '')
    raise ValueError('Wklej link do konkretnego filmu YouTube lub Vimeo.')


class FeaturedVideo(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool = False
    url: str = Field(default='', max_length=1000)
    title: str = Field(default='Przeżyjmy to jeszcze raz', max_length=160)
    description: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def validate_video(self):
        self.url = self.url.strip()
        self.title = self.title.strip() or 'Przeżyjmy to jeszcze raz'
        if self.enabled and not self.url:
            raise ValueError('Dodaj link do filmu albo wyłącz sekcję wideo.')
        video_embed_url(self.url)
        return self

    @property
    def embed_url(self):
        return video_embed_url(self.url)


def get_featured_video(db):
    setting = db.get(SystemSetting, VIDEO_KEY)
    try:
        return FeaturedVideo.model_validate_json(setting.value) if setting else FeaturedVideo()
    except ValueError:
        return FeaturedVideo()

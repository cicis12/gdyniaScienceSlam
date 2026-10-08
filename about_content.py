"""Editable timeline with defaults for sites that have not configured it yet."""
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from models import SystemSetting

ABOUT_KEY = 'about_timeline'
MAX_ENTRIES = 50


class TimelineEntry(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    id: str = Field(default_factory=lambda: uuid4().hex, pattern=r'^[a-z0-9_-]{1,64}$')
    label: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=10000)
    photo: str = Field(pattern=r'^/static/(?:assets/images|uploads)/[a-zA-Z0-9_./-]+\.(?:webp|png|jpg|jpeg)$')
    sort_order: int = Field(default=0, ge=0, le=100000)


DEFAULT_ENTRIES = [
    dict(id='idea', label='Idea', title='Czym jest Science Slam?', sort_order=0,
         photo='/static/assets/images/gallery15.webp',
         description='Gdynia Science Slam to konferencja, która daje młodym ludziom przestrzeń do dzielenia się wiedzą i rozwijania swoich pasji. Każdy prelegent ma 10 minut, by przedstawić wybrany przez siebie temat — na swój własny sposób.'),
    dict(id='poczatki', label='Początki', title='Jak to się zaczęło?', sort_order=1,
         photo='/static/assets/images/gallery1.webp',
         description='Pierwsza edycja powstała z inicjatywy Kornelii Wieczorek. Gdynia Science Slam miał być odpowiedzią na potrzebę stworzenia w Trójmieście miejsca, w którym młodzi naukowcy z całego regionu mogą zabrać głos.'),
    dict(id='rozwoj', label='Rozwój', title='Ze szkolnej auli na większą scenę', sort_order=2,
         photo='/static/assets/images/gallery2.webp',
         description='Po sukcesie pierwszej konferencji, zorganizowanej przez uczniów Gdyńskiej Trójki, funkcję lidera przejął Oskar Kotela. Przeniósł wydarzenie do Pomorskiego Parku Naukowo-Technologicznego i rozwinął program wystąpień.\n\nDziś kontynuujemy tę ideę, wspierając młode osoby z Gdyni, Trójmiasta i całej Polski.'),
    dict(id='dolacz', label='Twoja kolej', title='Czy to dla Ciebie?', sort_order=3,
         photo='/static/assets/images/gallery14.webp',
         description='Szukasz okazji, żeby się wykazać? Lubisz wyzwania? A może potrzebujesz miejsca, w którym ktoś Cię usłyszy?\n\nPodziel się tym, co Cię fascynuje, i dołącz do kolejnej edycji Gdynia Science Slam.'),
]
ENTRY_LIST = TypeAdapter(list[TimelineEntry])


def get_timeline(db):
    setting = db.get(SystemSetting, ABOUT_KEY)
    entries = ENTRY_LIST.validate_json(setting.value) if setting else ENTRY_LIST.validate_python(DEFAULT_ENTRIES)
    return sorted(entries, key=lambda entry: entry.sort_order)


def save_timeline(db, entries):
    db.merge(SystemSetting(key=ABOUT_KEY, value=ENTRY_LIST.dump_json(entries).decode()))

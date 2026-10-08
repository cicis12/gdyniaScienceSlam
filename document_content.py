"""Public PDF metadata and private uploads, with defaults for existing documents."""
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import re

from pydantic import BaseModel, ConfigDict, Field, StrictBool, TypeAdapter, field_validator
from pypdf import PdfReader
from models import SystemSetting

BASE_DIR = Path(__file__).resolve().parent
STATIC_DOCUMENTS_DIR = BASE_DIR / 'static/documents'
DOCUMENTS_DIR = BASE_DIR / 'uploads/documents'
DOCUMENTS_KEY = 'documents_content'
MAX_DOCUMENTS = 100
MAX_PDF_BYTES = 20 * 1024 * 1024


class Document(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    id: str = Field(default_factory=lambda: uuid4().hex, pattern=r'^[a-z0-9_-]{1,64}$')
    title: str = Field(min_length=1, max_length=160)
    year: int = Field(default=2026, ge=2000, le=2100)
    file: str = Field(max_length=300)
    filename: str = Field(min_length=1, max_length=180)
    enabled: StrictBool = True
    sort_order: int = Field(default=0, ge=0, le=100000)

    @field_validator('file')
    @classmethod
    def valid_file(cls, value):
        if value.startswith('static/documents/'):
            name = value.removeprefix('static/documents/')
            if not name.lower().endswith('.pdf') or '/' in name or '\\' in name or any(ord(char) < 32 for char in name):
                raise ValueError('Nieprawidłowa ścieżka dokumentu.')
        elif not re.fullmatch(r'uploads/documents/[a-f0-9]{32}\.pdf', value):
            raise ValueError('Nieprawidłowa ścieżka dokumentu.')
        return value

    @field_validator('filename')
    @classmethod
    def valid_filename(cls, value):
        if not value.lower().endswith('.pdf') or any(char in value for char in '/\\') or any(ord(char) < 32 for char in value):
            raise ValueError('Nieprawidłowa nazwa pliku PDF.')
        return value


DEFAULT_DOCUMENTS = [
    dict(id=id, title=title, file='static/documents/' + filename, filename=filename, year=2026, sort_order=index)
    for index, (id, title, filename) in enumerate((
        ('regulamin', 'Regulamin wydarzenia', 'Regulamin.pdf'),
        ('prywatnosc', 'Polityka prywatności', 'Polityka prywatności .pdf'),
        ('opiekun', 'Zgłoszenie na opiekuna prelegenta', 'Zgłoszenie na opiekuna prelegenta GSS 2026.pdf'),
        ('wizerunek-niepelnoletni', 'Zgoda na wykorzystanie wizerunku (uczestnik niepełnoletni)', 'Zgoda na wykorzystanie wizerunku (uczestnik niepelnoletni).pdf'),
        ('wizerunek-pelnoletni', 'Zgoda na wykorzystanie wizerunku (uczestnik pełnoletni)', 'Zgoda na wykorzystanie wizerunku (uczestnik pełnoletni).pdf'),
        ('zgoda-rodzica', 'Zgoda rodzica na udział w wydarzeniu', 'Zgoda rodzica na udzial w GSS2026.pdf'),
    ))
]
DOCUMENT_LIST = TypeAdapter(list[Document])


def get_documents(db):
    setting = db.get(SystemSetting, DOCUMENTS_KEY)
    documents = DOCUMENT_LIST.validate_json(setting.value) if setting else DOCUMENT_LIST.validate_python(DEFAULT_DOCUMENTS)
    return sorted(documents, key=lambda document: (-document.year, document.sort_order, document.id))


def save_documents(db, documents):
    documents = DOCUMENT_LIST.validate_python([document.model_dump() for document in documents])
    if len(documents) > MAX_DOCUMENTS or len({document.id for document in documents}) != len(documents):
        raise ValueError('Za dużo dokumentów lub powtórzone identyfikatory.')
    db.merge(SystemSetting(key=DOCUMENTS_KEY, value=DOCUMENT_LIST.dump_json(documents).decode()))


def document_path(document):
    directory = STATIC_DOCUMENTS_DIR if document.file.startswith('static/documents/') else DOCUMENTS_DIR
    path = (directory / Path(document.file).name).resolve()
    if not path.is_relative_to(directory.resolve()):
        raise ValueError('Nieprawidłowa ścieżka dokumentu.')
    return path


def validate_pdf(data):
    if not data or len(data) > MAX_PDF_BYTES:
        raise ValueError('Dokument może mieć maksymalnie 20 MB.')
    if not data.startswith(b'%PDF-'):
        raise ValueError('Wybierz poprawny plik PDF.')
    try:
        reader = PdfReader(BytesIO(data), strict=True)
        unlocked = not reader.is_encrypted or bool(reader.decrypt(''))
        pages = len(reader.pages) if unlocked else 0
    except Exception:
        raise ValueError('Nie można odczytać pliku PDF.') from None
    if not unlocked:
        raise ValueError('Usuń hasło z dokumentu przed przesłaniem.')
    if not 1 <= pages <= 2000:
        raise ValueError('Dokument musi zawierać od 1 do 2000 stron.')
    return data

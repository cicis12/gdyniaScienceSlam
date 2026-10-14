"""Private form attachments with bounded storage and server-generated names."""
import fcntl
import os
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

UPLOAD_DIR = Path(__file__).resolve().parent / 'uploads' / 'forms'
MAX_FILE_SIZE = 100 * 1024 * 1024
MAX_STORAGE_SIZE = int(os.getenv('FORM_UPLOAD_STORAGE_LIMIT_MB', '10240')) * 1024 * 1024
from file_types import FILE_TYPES, DEFAULT_FILE_CATEGORIES, allowed_extensions


def valid_header(extension, header):
    if extension in {'.mp4', '.mov'}:
        return len(header) >= 12 and header[4:8] == b'ftyp'
    if extension in {'.webm', '.mkv'}:
        return header.startswith(b'\x1aE\xdf\xa3')
    if extension == '.pdf':
        return header.startswith(b'%PDF-')
    if extension == '.png':
        return header.startswith(b'\x89PNG\r\n\x1a\n')
    if extension in {'.jpg', '.jpeg'}:
        return header.startswith(b'\xff\xd8\xff')
    if extension == '.webp':
        return header.startswith(b'RIFF') and header[8:12] == b'WEBP'
    if extension == '.gif':
        return header.startswith((b'GIF87a', b'GIF89a'))
    if extension in {'.zip', '.docx', '.xlsx', '.pptx', '.odt', '.ods', '.odp'}:
        return header.startswith((b'PK\x03\x04', b'PK\x05\x06'))
    if extension in {'.doc', '.xls', '.ppt'}:
        return header.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1')
    if extension == '.rar':
        return header.startswith((b'Rar!\x1a\x07\x00', b'Rar!\x1a\x07\x01\x00'))
    if extension == '.7z':
        return header.startswith(b'7z\xbc\xaf\x27\x1c')
    if extension == '.gz':
        return header.startswith(b'\x1f\x8b')
    if extension == '.tar':
        return header[257:262] == b'ustar'
    if extension == '.rtf':
        return header.startswith(b'{\\rtf')
    if extension in {'.txt', '.csv'}:
        import codecs
        try:
            codecs.getincrementaldecoder('utf-8')().decode(header)
            return b'\x00' not in header
        except UnicodeDecodeError:
            return False
    return False


def remove_uploads(records):
    for record in records.values():
        (UPLOAD_DIR / record['stored_name']).unlink(missing_ok=True)


def save_uploads(uploads, accepted_types=None):
    records = {}
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Serialize storage reservation across app workers, including when using Redis.
    with (UPLOAD_DIR / '.storage.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        used = sum(path.stat().st_size for path in UPLOAD_DIR.iterdir() if path.is_file())
        incoming = sum(upload.size or 0 for upload in uploads.values())
        if used + incoming > MAX_STORAGE_SIZE:
            raise HTTPException(503, 'Przesyłanie plików jest chwilowo niedostępne. Skontaktuj się z organizatorem.')
        try:
            for field, upload in uploads.items():
                original = (upload.filename or '').replace('\\', '/').split('/')[-1]
                original = ''.join(c for c in original if ord(c) >= 32)[:200]
                extension = Path(original).suffix.lower()
                upload.file.seek(0)
                header = upload.file.read(512)
                upload.file.seek(0)
                categories = accepted_types[field] if accepted_types is not None else DEFAULT_FILE_CATEGORIES
                if extension not in allowed_extensions(categories) or not valid_header(extension, header):
                    raise HTTPException(422, 'Format pliku nie pasuje do typów dozwolonych w tym polu.')
                if not upload.size or upload.size > MAX_FILE_SIZE:
                    raise HTTPException(413, 'Plik musi być niepusty i nie większy niż 100 MB.')
                name = f'{uuid4().hex}{extension}'
                record = {'kind': 'attachment', 'stored_name': name, 'filename': original,
                          'media_type': FILE_TYPES[extension], 'size': upload.size}
                records[field] = record
                total = 0
                with os.fdopen(os.open(UPLOAD_DIR / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as output:
                    while chunk := upload.file.read(1024 * 1024):
                        total += len(chunk)
                        if total > MAX_FILE_SIZE or used + total > MAX_STORAGE_SIZE:
                            raise HTTPException(413, 'Plik jest zbyt duży (maksymalnie 100 MB).')
                        output.write(chunk)
                record['size'] = total
                used += total
        except BaseException:
            remove_uploads(records)
            raise
    return records


def attachment_path(record):
    name = record.get('stored_name', '')
    # Never serve user-selected paths or uploaded HTML/SVG as active content.
    if len(name) > 40 or Path(name).name != name or Path(name).suffix not in FILE_TYPES:
        raise HTTPException(404)
    path = (UPLOAD_DIR / name).resolve()
    if path.parent != UPLOAD_DIR.resolve() or not path.is_file():
        raise HTTPException(404)
    return path

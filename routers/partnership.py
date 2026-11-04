"""Public partner invitation and superadmin section editor."""
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from database import get_db
from image_uploads import MAX_IMAGE_BYTES, normalize_image
from partnership_content import SECTION_TYPES, PartnershipConfig, get_partnership, save_partnership
from templating import create_templates
import mail

templates = create_templates()
PHOTO_DIR = Path(__file__).resolve().parents[1] / 'static/uploads/partnership'
public_router = APIRouter()


@public_router.get('/become-a-partner')
def page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, 'client/become_partner.html', {
        'request': request, 'page_name': 'become_partner',
        'header_title': 'Zostań partnerem - Gdynia Science Slam', 'config': get_partnership(db),
    })


class ContactMessage(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=160, pattern=r'^[^\r\n]+$')
    email: EmailStr = Field(max_length=254)
    topic: str = Field(min_length=1, max_length=200, pattern=r'^[^\r\n]+$')
    content: str = Field(min_length=1, max_length=10000)
    website: str = Field(default='', max_length=500)  # Honeypot; never sent.


@public_router.post('/become-a-partner/contact/{section_id}')
def contact(section_id: str, message: ContactMessage, db: Session = Depends(get_db)):
    config = get_partnership(db)
    if not any(s.id == section_id and s.type == 'contact' and s.enabled for s in config.sections):
        raise HTTPException(404)
    if message.website:
        raise HTTPException(422, 'Nieprawidłowe zgłoszenie.')
    if not config.recipient or not mail.API_KEY or not mail.EMAIL_FROM:
        raise HTTPException(503, 'Formularz kontaktowy jest chwilowo niedostępny. Spróbuj ponownie później.')
    try:
        mail.send_partner_message(config.recipient, message.name, str(message.email), message.topic, message.content)
    except (mail.requests.RequestException, RuntimeError):
        raise HTTPException(502, 'Nie udało się wysłać wiadomości. Spróbuj ponownie później.') from None
    return {'message': 'Wiadomość została przyjęta do wysłania. Dziękujemy za kontakt!'}


def build_admin_router(require_superadmin):
    router = APIRouter(prefix='/admin/become-a-partner', dependencies=[Depends(require_superadmin)])

    @router.get('')
    def editor(request: Request, db: Session = Depends(get_db), admin=Depends(require_superadmin)):
        return templates.TemplateResponse(request, 'admin/become_partner.html', {
            'request': request, 'admin': admin, 'config': get_partnership(db), 'section_types': SECTION_TYPES,
        })

    async def read_draft(request, db, preview=False):
        import base64
        from starlette.datastructures import UploadFile
        new_paths = []
        try:
            async with request.form(max_files=1001, max_fields=10, max_part_size=5 * 1024 * 1024) as form:
                config = PartnershipConfig.model_validate_json(form.get('config', ''))
                targets = [('feature_photo', config, 'feature_photo')]
                targets += [(f'photo:{section.id}:{person.id}', person, 'photo')
                            for section in config.sections if section.type == 'person' for person in section.people]
                targets += [(f'paragraph_photo:{section.id}', section, 'photo')
                            for section in config.sections if section.type == 'paragraph']
                images = []
                for key, target, attribute in targets:
                    photo = form.get(key)
                    if photo is not None and not isinstance(photo, UploadFile):
                        raise ValueError('Nieprawidłowy plik zdjęcia.')
                    if photo and photo.filename:
                        data = await run_in_threadpool(normalize_image, await photo.read(MAX_IMAGE_BYTES + 1))
                        images.append((target, attribute, data))
                # Validate the whole page before writing any files or committing content.
                uploaded = {id(target) for target, _, _ in images}
                for section in config.sections:
                    if not section.enabled:
                        continue
                    if section.type == 'person' and (not section.people or any(
                            not p.name or not p.occupation or (not p.photo and id(p) not in uploaded) for p in section.people)):
                        raise ValueError('Dodaj zdjęcie, imię i nazwisko oraz stanowisko każdej osoby w widocznej sekcji.')
                    if section.type == 'heading' and not section.title:
                        raise ValueError('Wpisz tekst dużego nagłówka.')
                    if section.type == 'icons' and any(not item.svg or not item.text for item in section.items):
                        raise ValueError('Dodaj ikonę i tekst do każdej kolumny.')
                for target, attribute, data in images:
                    if preview:
                        setattr(target, attribute, 'data:image/webp;base64,' + base64.b64encode(data).decode())
                    else:
                        PHOTO_DIR.mkdir(parents=True, exist_ok=True)
                        path = PHOTO_DIR / (uuid4().hex + '.webp')
                        new_paths.append(path)
                        path.write_bytes(data)
                        setattr(target, attribute, '/static/uploads/partnership/' + path.name)
                config.sections.sort(key=lambda section: section.sort_order)
                if not preview:
                    save_partnership(db, config)
                    db.commit()
                return config
        except Exception as error:
            db.rollback()
            for path in new_paths:
                path.unlink(missing_ok=True)
            if isinstance(error, ValueError):
                raise HTTPException(422, 'Nie zapisano zmian. Sprawdź pola, ikony SVG i zdjęcia. ' + str(error)[:500]) from None
            raise

    @router.post('/save')
    async def save(request: Request, db: Session = Depends(get_db)):
        config = await read_draft(request, db)
        return {'message': 'Wszystkie zmiany zostały zapisane.', 'config': config.model_dump()}

    @router.post('/preview')
    async def preview(request: Request, db: Session = Depends(get_db)):
        config = await read_draft(request, db, preview=True)
        return templates.TemplateResponse(request, 'client/become_partner.html', {
            'request': request, 'page_name': 'become_partner', 'header_title': 'Podgląd — Zostań partnerem',
            'config': config, 'preview': True,
        }, headers={'Cache-Control': 'no-store'})

    return router

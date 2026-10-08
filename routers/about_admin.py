from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from about_content import MAX_ENTRIES, TimelineEntry, get_timeline, save_timeline
from database import get_db
from image_uploads import MAX_IMAGE_BYTES, normalize_image
from templating import create_templates

PHOTO_DIR = Path(__file__).resolve().parents[1] / 'static/uploads/about'
templates = create_templates()


def build_router(require_superadmin):
    router = APIRouter(prefix='/admin/about', dependencies=[Depends(require_superadmin)])

    def render(request, db, admin, error=None, status_code=200):
        return templates.TemplateResponse('admin/about.html', {
            'request': request, 'admin': admin, 'entries': get_timeline(db), 'error': error,
        }, status_code=status_code)

    @router.get('')
    def dashboard(request: Request, db: Session = Depends(get_db), admin=Depends(require_superadmin)):
        return render(request, db, admin)

    async def store(request, db, admin, entry_id, label, title, description, sort_order, photo):
        entries = get_timeline(db)
        existing = next((entry for entry in entries if entry.id == entry_id), None)
        if entry_id is not None and existing is None:
            raise HTTPException(404)
        path = None
        try:
            if existing is None and len(entries) >= MAX_ENTRIES:
                raise ValueError('Możesz dodać maksymalnie 50 etapów.')
            # Validate text before writing an uploaded image.
            entry = TimelineEntry(id=entry_id or uuid4().hex, label=label, title=title,
                                  description=description, sort_order=sort_order,
                                  photo=existing.photo if existing else '/static/uploads/about/new.webp')
            if photo and photo.filename:
                data = normalize_image(await photo.read(MAX_IMAGE_BYTES + 1))
                PHOTO_DIR.mkdir(parents=True, exist_ok=True)
                path = PHOTO_DIR / f'{uuid4().hex}.webp'
                path.write_bytes(data)
                entry.photo = '/static/uploads/about/' + path.name
            elif existing is None:
                raise ValueError('Dodaj zdjęcie nowego etapu.')
            entries = [entry if item.id == entry.id else item for item in entries] if existing else [*entries, entry]
            save_timeline(db, entries)
            db.commit()
        except Exception as exc:
            db.rollback()
            if path:
                path.unlink(missing_ok=True)
            if isinstance(exc, ValueError):
                return render(request, db, admin, error='Nie zapisano etapu. Sprawdź wymagane pola i zdjęcie. ' + str(exc)[:250], status_code=422)
            raise
        return RedirectResponse('/admin/about?saved=1#entry-' + entry.id, 303)

    @router.post('/entries')
    async def add(request: Request, label: str = Form(...), title: str = Form(...), description: str = Form(...),
                  sort_order: int = Form(...), photo: UploadFile = File(...),
                  db: Session = Depends(get_db), admin=Depends(require_superadmin)):
        return await store(request, db, admin, None, label, title, description, sort_order, photo)

    @router.post('/entries/{entry_id}')
    async def edit(request: Request, entry_id: str, label: str = Form(...), title: str = Form(...),
                   description: str = Form(...), sort_order: int = Form(...), photo: UploadFile | None = File(None),
                   db: Session = Depends(get_db), admin=Depends(require_superadmin)):
        return await store(request, db, admin, entry_id, label, title, description, sort_order, photo)

    @router.post('/entries/{entry_id}/delete')
    def delete(entry_id: str, db: Session = Depends(get_db)):
        entries = get_timeline(db)
        if not any(entry.id == entry_id for entry in entries):
            raise HTTPException(404)
        save_timeline(db, [entry for entry in entries if entry.id != entry_id])
        db.commit()
        return RedirectResponse('/admin/about?saved=1', 303)

    return router

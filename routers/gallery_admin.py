from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import GalleryPhoto, SystemSetting
from gallery import FeaturedVideo, VIDEO_KEY, get_featured_video
from image_uploads import MAX_IMAGE_BYTES, normalize_image
from templating import create_templates

PHOTO_DIR = Path(__file__).resolve().parents[1] / 'static/uploads/gallery'
templates = create_templates()


def build_router(require_superadmin):
    router = APIRouter(prefix='/admin/gallery', dependencies=[Depends(require_superadmin)])

    def render(request, db, admin, error=None, video=None, status_code=200):
        return templates.TemplateResponse('admin/gallery.html', {
            'request': request, 'admin': admin, 'error': error,
            'photos': db.query(GalleryPhoto).order_by(GalleryPhoto.year.desc(), GalleryPhoto.sort_order, GalleryPhoto.id).all(),
            'video': video or get_featured_video(db),
        }, status_code=status_code)

    @router.get('')
    def dashboard(request: Request, db: Session = Depends(get_db), admin=Depends(require_superadmin)):
        return render(request, db, admin)

    @router.post('/photos')
    async def upload(request: Request, year: int = Form(..., ge=2000, le=2100),
                     caption: str = Form('', max_length=300), photos: list[UploadFile] = File(...),
                     db: Session = Depends(get_db), admin=Depends(require_superadmin)):
        paths = []
        try:
            if not 1 <= len(photos) <= 30:
                raise ValueError('Dodaj od 1 do 30 zdjęć jednocześnie.')
            start = db.query(func.max(GalleryPhoto.sort_order)).filter(GalleryPhoto.year == year).scalar()
            start = (start + 1) if start is not None else 0
            for index, photo in enumerate(photos):
                data = normalize_image(await photo.read(MAX_IMAGE_BYTES + 1))
                PHOTO_DIR.mkdir(parents=True, exist_ok=True)
                path = PHOTO_DIR / f'{uuid4().hex}.webp'
                paths.append(path)
                path.write_bytes(data)
                db.add(GalleryPhoto(year=year, caption=caption.strip(), sort_order=start + index,
                                    photo='/static/uploads/gallery/' + path.name))
            db.commit()
        except Exception as exc:
            db.rollback()
            for path in paths:
                path.unlink(missing_ok=True)
            if isinstance(exc, ValueError):
                return render(request, db, admin, error=str(exc), status_code=422)
            raise
        return RedirectResponse('/admin/gallery?saved=1#photos', 303)

    @router.post('/photos/{photo_id}')
    def edit(photo_id: int, year: int = Form(..., ge=2000, le=2100), caption: str = Form('', max_length=300),
             sort_order: int = Form(..., ge=0, le=100000), db: Session = Depends(get_db)):
        photo = db.get(GalleryPhoto, photo_id)
        if photo is None:
            raise HTTPException(404)
        photo.year, photo.caption, photo.sort_order = year, caption.strip(), sort_order
        db.commit()
        return RedirectResponse('/admin/gallery?saved=1#photos', 303)

    @router.post('/photos/{photo_id}/delete')
    def delete(photo_id: int, db: Session = Depends(get_db)):
        photo = db.get(GalleryPhoto, photo_id)
        if photo is None:
            raise HTTPException(404)
        db.delete(photo)
        db.commit()
        return RedirectResponse('/admin/gallery?saved=1#photos', 303)

    @router.post('/video')
    def save_video(request: Request, enabled: bool = Form(False), url: str = Form('', max_length=1000),
                   title: str = Form('', max_length=160), description: str = Form('', max_length=2000),
                   db: Session = Depends(get_db), admin=Depends(require_superadmin)):
        data = dict(enabled=enabled, url=url, title=title, description=description)
        try:
            video = FeaturedVideo(**data)
        except ValueError:
            return render(request, db, admin, error='Podaj poprawny link HTTPS do filmu YouTube lub Vimeo.', video=data, status_code=422)
        db.merge(SystemSetting(key=VIDEO_KEY, value=video.model_dump_json()))
        db.commit()
        return RedirectResponse('/admin/gallery?saved=1#video', 303)

    return router

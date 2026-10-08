"""Superadmin content management; public visibility is enforced in main."""
from pathlib import Path
from typing import Literal
from uuid import uuid4
from io import BytesIO
import warnings
import json

from PIL import Image, UnidentifiedImageError

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from templating import create_templates
from sqlalchemy.orm import Session

from database import get_db
from models import FormInfo, SystemSetting, TeamMember
from site_pages import PUBLIC_PAGES, page_visibility
from partner_content import get_partners
from home_images import HomeImage, HomeImages, IMAGE_SLOTS, IMAGE_POSITIONS, get_home_images, save_home_images
from image_uploads import normalize_image, MAX_IMAGE_BYTES
from starlette.concurrency import run_in_threadpool
from system_settings import (COLOR_GROUPS, DEFAULT_THEME, DEFAULT_FOOTER, DEFAULT_HOME, HOME_FIELDS,
                             THEME_KEY, FOOTER_KEY, HOME_KEY, PAGE_MODES_KEY, DEFAULT_PAGE_MODES, DISPLAY_MODES, load_public_settings, validate_settings)
from team_theme import COLOR_FIELDS, DEFAULT_PALETTE, PALETTE_KEY, DETAILS_KEY, get_team_palette, valid_color, team_details_enabled

PHOTO_DIR = Path(__file__).resolve().parents[1] / 'static' / 'uploads' / 'team'
HOME_PHOTO_DIR = Path(__file__).resolve().parents[1] / 'static/uploads/home'
MAX_PHOTO_SIZE = 5 * 1024 * 1024

templates = create_templates()


async def save_photo(photo):
    data = await photo.read(MAX_PHOTO_SIZE + 1)
    if len(data) > MAX_PHOTO_SIZE:
        raise HTTPException(422, 'Zdjęcie może mieć maksymalnie 5 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format not in {'JPEG', 'PNG', 'WEBP'} or image.width * image.height > 20_000_000:
                    raise ValueError('Unsupported image')
                image.load()
                image.thumbnail((1600, 1600))
                output = BytesIO()
                image.convert('RGB').save(output, format='WEBP', quality=88)
                data = output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(422, 'Wybierz zdjęcie JPG, PNG lub WebP.')
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    filename = f'{uuid4().hex}.webp'
    (PHOTO_DIR / filename).write_bytes(data)
    return '/static/uploads/team/' + filename


def build_router(require_superadmin):
    router = APIRouter(prefix='/admin/content', dependencies=[Depends(require_superadmin)])

    @router.get('')
    def content(request: Request, db: Session = Depends(get_db), admin=Depends(require_superadmin)):
        event = db.get(SystemSetting, 'event_datetime')
        return templates.TemplateResponse('admin/site_content.html', {
            'request': request, 'admin': admin, 'pages': PUBLIC_PAGES,
            'visibility': page_visibility(db),
            'forms': db.query(FormInfo).order_by(FormInfo.name).all(),
            'site_settings': load_public_settings(db), 'color_groups': COLOR_GROUPS,
            'event_datetime': event.value if event else '',
        })

    @router.get('/preview')
    def preview(request: Request, db: Session = Depends(get_db)):
        event = db.get(SystemSetting, 'event_datetime')
        return templates.TemplateResponse('client/index.html', {
            'request': request, 'page_name': 'home', 'header_title': 'Podgląd strony',
            'event_datetime': event.value if event else '',
            'carousel_partners': get_partners(db).carousel_partners,
            'home_images': get_home_images(db),
            'members': db.query(TeamMember).order_by(TeamMember.id).all(),
        })

    @router.get('/team')
    def team_editor(request: Request, db: Session = Depends(get_db), admin=Depends(require_superadmin)):
        return templates.TemplateResponse('admin/team_settings.html', {
            'request': request, 'admin': admin,
            'members': db.query(TeamMember).order_by(TeamMember.id).all(),
            'team_palette': get_team_palette(db), 'color_fields': COLOR_FIELDS,
            'team_details_enabled': team_details_enabled(db),
        })

    def render_home(request, db, admin, error=None, status_code=200):
        return templates.TemplateResponse('admin/home_settings.html', {
            'request': request, 'admin': admin, 'home_fields': HOME_FIELDS,
            'home_content': load_public_settings(db)['home'],
            'home_images': get_home_images(db), 'image_slots': IMAGE_SLOTS, 'image_positions': IMAGE_POSITIONS,
            'error': error,
        }, status_code=status_code)

    @router.get('/home')
    def home_editor(request: Request, db: Session = Depends(get_db), admin=Depends(require_superadmin)):
        return render_home(request, db, admin)

    async def save_setting(request, db, key, defaults, destination):
        form = await request.form()
        try:
            values = validate_settings(key, {name: form.get(name, '') for name in defaults})
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        db.merge(SystemSetting(key=key, value=json.dumps(values, ensure_ascii=False)))
        db.commit()
        return RedirectResponse(destination, 303)

    @router.post('/page-modes')
    async def save_page_modes(request: Request, db: Session = Depends(get_db)):
        return await save_setting(request, db, PAGE_MODES_KEY, DEFAULT_PAGE_MODES, '/admin/content?saved=1#colors')

    @router.post('/page-mode/{page}')
    def save_page_mode(page: str, mode: str = Form(...), db: Session = Depends(get_db)):
        if page not in DEFAULT_PAGE_MODES or mode not in DISPLAY_MODES:
            raise HTTPException(422, 'Nieprawidłowa strona lub tryb wyświetlania.')
        modes = load_public_settings(db)['page_modes']
        modes[page] = mode
        db.merge(SystemSetting(key=PAGE_MODES_KEY, value=json.dumps(modes)))
        db.commit()
        destination = {
            'team': '/admin/content/team',
            'about': '/admin/about', 'previous_editions': '/admin/gallery',
            'partners': '/admin/partners',
            'documents': '/admin/documents',
        }.get(page, '/admin/content')
        return RedirectResponse(destination + '?saved=1' + ('#colors' if destination == '/admin/content' else ''), 303)

    @router.post('/theme')
    async def save_theme(request: Request, db: Session = Depends(get_db)):
        return await save_setting(request, db, THEME_KEY, DEFAULT_THEME, '/admin/content?saved=1#colors')

    @router.post('/theme/reset')
    def reset_theme(db: Session = Depends(get_db)):
        setting = db.get(SystemSetting, THEME_KEY)
        if setting:
            db.delete(setting)
            db.commit()
        return RedirectResponse('/admin/content?saved=1#colors', 303)

    @router.post('/footer')
    async def save_footer(request: Request, db: Session = Depends(get_db)):
        return await save_setting(request, db, FOOTER_KEY, DEFAULT_FOOTER, '/admin/content?saved=1#footer')

    @router.post('/home')
    async def save_home(request: Request, db: Session = Depends(get_db)):
        return await save_setting(request, db, HOME_KEY, DEFAULT_HOME, '/admin/content/home?saved=1')

    @router.get('/{page}/placeholder')
    def placeholder(page: str, request: Request, admin=Depends(require_superadmin)):
        if page == 'partners':
            return RedirectResponse('/admin/partners', 303)
        if page == 'documents':
            return RedirectResponse('/admin/documents', 303)
        raise HTTPException(404)

    @router.post('/home/images/{slot}')
    async def save_home_image(slot: str, request: Request, alt: str = Form('', max_length=300),
                              position: Literal['center', 'top', 'bottom', 'left', 'right'] = Form('center'),
                              photo: UploadFile | None = File(None), db: Session = Depends(get_db), admin=Depends(require_superadmin)):
        if slot not in {key for key, _ in IMAGE_SLOTS}:
            raise HTTPException(404)
        images = get_home_images(db)
        current = getattr(images, slot)
        updated = HomeImage(photo=current.photo, alt=alt, position=position)
        new_path = None
        try:
            if photo and photo.filename:
                data = await run_in_threadpool(normalize_image, await photo.read(MAX_IMAGE_BYTES + 1))
                HOME_PHOTO_DIR.mkdir(parents=True, exist_ok=True)
                new_path = HOME_PHOTO_DIR / (uuid4().hex + '.webp')
                new_path.write_bytes(data)
                updated.photo = '/static/uploads/home/' + new_path.name
            setattr(images, slot, updated)
            save_home_images(db, images)
            db.commit()
        except Exception as error:
            db.rollback()
            if new_path:
                new_path.unlink(missing_ok=True)
            if isinstance(error, ValueError):
                return render_home(request, db, admin, str(error), 422)
            raise
        return RedirectResponse('/admin/content/home?saved=1&image=' + slot + '#home-image-' + slot, 303)

    @router.post('/home/images/{slot}/reset')
    def reset_home_image(slot: str, db: Session = Depends(get_db)):
        if slot not in {key for key, _ in IMAGE_SLOTS}:
            raise HTTPException(404)
        images = get_home_images(db)
        setattr(images, slot, getattr(HomeImages(), slot))
        save_home_images(db, images)
        db.commit()
        return RedirectResponse('/admin/content/home?saved=1&image=' + slot + '#home-image-' + slot, 303)

    @router.post('/team-settings')
    def save_team_settings(details_enabled: bool = Form(False), db: Session = Depends(get_db)):
        db.merge(SystemSetting(key=DETAILS_KEY, value='true' if details_enabled else 'false'))
        db.commit()
        return RedirectResponse('/admin/content/team?saved=1#team', 303)

    @router.post('/palette')
    async def save_palette(request: Request, db: Session = Depends(get_db)):
        form = await request.form()
        palette = {key: form.get(key) for key in DEFAULT_PALETTE}
        if not all(valid_color(value) for value in palette.values()):
            raise HTTPException(422, 'Wybierz poprawne kolory w formacie #RRGGBB.')
        db.merge(SystemSetting(key=PALETTE_KEY, value=json.dumps({key: value.lower() for key, value in palette.items()})))
        db.commit()
        return RedirectResponse('/admin/content/team?saved=1#colors', 303)

    @router.post('/palette/reset')
    def reset_palette(db: Session = Depends(get_db)):
        setting = db.get(SystemSetting, PALETTE_KEY)
        if setting:
            db.delete(setting)
            db.commit()
        return RedirectResponse('/admin/content/team?saved=1#colors', 303)

    @router.post('/pages')
    def save_pages(visible: list[str] = Form(default=[]), db: Session = Depends(get_db)):
        if set(visible) - {key for key, _, _ in PUBLIC_PAGES}:
            raise HTTPException(422, 'Nieznana strona.')
        for key, _, _ in PUBLIC_PAGES:
            db.merge(SystemSetting(key='page_visible:' + key, value='true' if key in visible else 'false'))
        db.commit()
        return RedirectResponse('/admin/content?saved=1#pages', 303)

    @router.post('/forms/{form_id}')
    def save_form_visibility(form_id: int, enabled: bool = Form(False), db: Session = Depends(get_db)):
        form = db.get(FormInfo, form_id)
        if form is None:
            raise HTTPException(404)
        form.enabled = enabled
        db.commit()
        return RedirectResponse('/admin/content?saved=1#pages', 303)

    async def store_member(member, name, position, description, photo, db):
        name, position, description = name.strip(), position.strip(), description.strip()
        if not name or not position or not description or len(name) > 160 or len(position) > 160 or len(description) > 10000:
            raise HTTPException(422, 'Wypełnij imię i nazwisko, stanowisko (do 160 znaków) oraz opis (do 10000 znaków).')
        photo_path = None
        if photo and photo.filename:
            photo_path = await save_photo(photo)
        if not member.photo and not photo_path:
            raise HTTPException(422, 'Dodaj zdjęcie członka zespołu.')
        member.name, member.position, member.description = name, position, description
        if photo_path:
            member.photo = photo_path
        try:
            db.add(member)
            db.commit()
        except Exception:
            db.rollback()
            if photo_path:
                (PHOTO_DIR / Path(photo_path).name).unlink(missing_ok=True)
            raise
        return RedirectResponse('/admin/content/team?saved=1#team', 303)

    @router.post('/team')
    async def add_member(name: str = Form(...), position: str = Form(...), description: str = Form(...),
                         photo: UploadFile = File(...), db: Session = Depends(get_db)):
        return await store_member(TeamMember(), name, position, description, photo, db)

    @router.post('/team/{member_id}')
    async def edit_member(member_id: int, name: str = Form(...), position: str = Form(...),
                          description: str = Form(...), photo: UploadFile | None = File(None),
                          db: Session = Depends(get_db)):
        member = db.get(TeamMember, member_id)
        if member is None:
            raise HTTPException(404)
        return await store_member(member, name, position, description, photo, db)

    @router.post('/team/{member_id}/delete')
    def delete_member(member_id: int, db: Session = Depends(get_db)):
        member = db.get(TeamMember, member_id)
        if member is None:
            raise HTTPException(404)
        db.delete(member)
        db.commit()
        return RedirectResponse('/admin/content/team?saved=1#team', 303)

    return router

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from database import get_db
from image_uploads import MAX_IMAGE_BYTES
from partner_content import (Partner, PartnerSection, MAX_PARTNERS, MAX_SECTIONS,
                             get_partners, save_partners, normalize_logo)
from templating import create_templates

LOGO_DIR = Path(__file__).resolve().parents[1] / 'static/uploads/partners'
templates = create_templates()


def build_router(require_superadmin):
    router = APIRouter(prefix='/admin/partners', dependencies=[Depends(require_superadmin)])

    def render(request, db, admin, error=None, status_code=200):
        return templates.TemplateResponse('admin/partners.html', {
            'request': request, 'admin': admin, 'partner_config': get_partners(db), 'error': error,
        }, status_code=status_code)

    def section_for(config, section_id):
        section = next((item for item in config.sections if item.id == section_id), None)
        if section is None:
            raise HTTPException(404, 'Sekcja nie istnieje.')
        return section

    def commit(db, config, anchor=''):
        save_partners(db, config)
        db.commit()
        return RedirectResponse('/admin/partners?saved=1' + ('#' + anchor if anchor else ''), 303)

    @router.get('')
    def dashboard(request: Request, db: Session = Depends(get_db), admin=Depends(require_superadmin)):
        return render(request, db, admin)

    @router.post('/settings')
    def settings(enabled: bool = Form(False), db: Session = Depends(get_db)):
        config = get_partners(db)
        config.enabled = enabled
        return commit(db, config)

    @router.post('/sections')
    def add_section(request: Request, title: str = Form(...), highlighted: bool = Form(False),
                    enabled: bool = Form(False), sort_order: int = Form(0, ge=0, le=100000),
                    db: Session = Depends(get_db), admin=Depends(require_superadmin)):
        config = get_partners(db)
        try:
            if len(config.sections) >= MAX_SECTIONS:
                raise ValueError('Możesz dodać maksymalnie 50 sekcji.')
            config.sections.append(PartnerSection(title=title, highlighted=highlighted, enabled=enabled, sort_order=sort_order))
            return commit(db, config)
        except ValueError as error:
            db.rollback()
            return render(request, db, admin, str(error), 422)

    @router.post('/sections/{section_id}')
    def edit_section(section_id: str, title: str = Form(...), highlighted: bool = Form(False),
                     enabled: bool = Form(False), sort_order: int = Form(0, ge=0, le=100000),
                     db: Session = Depends(get_db)):
        config = get_partners(db)
        section = section_for(config, section_id)
        try:
            updated = PartnerSection(id=section.id, title=title, highlighted=highlighted, enabled=enabled,
                                     sort_order=sort_order, partners=section.partners)
        except ValueError:
            raise HTTPException(422, 'Wypełnij nazwę sekcji (do 160 znaków).') from None
        config.sections[config.sections.index(section)] = updated
        return commit(db, config, 'section-' + section_id)

    @router.post('/sections/{section_id}/delete')
    def delete_section(section_id: str, db: Session = Depends(get_db)):
        config = get_partners(db)
        config.sections.remove(section_for(config, section_id))
        return commit(db, config)

    async def store_partner(request, db, admin, config, source, partner_id, name, website, logo_scale, sort_order, section_id, logo):
        destination = section_for(config, section_id)
        original = next((item for item in source.partners if item.id == partner_id), None) if partner_id else None
        if partner_id and original is None:
            raise HTTPException(404, 'Partner nie istnieje.')
        new_path = None
        try:
            if not original and sum(len(section.partners) for section in config.sections) >= MAX_PARTNERS:
                raise ValueError('Możesz dodać maksymalnie 200 partnerów.')
            partner = Partner(id=original.id if original else uuid4().hex, name=name, website=website,
                              logo_scale=logo_scale, sort_order=sort_order,
                              logo=original.logo if original else '/static/uploads/partners/pending.webp')
            if logo and logo.filename:
                data, extension = normalize_logo(await logo.read(MAX_IMAGE_BYTES + 1), logo.filename)
                LOGO_DIR.mkdir(parents=True, exist_ok=True)
                new_path = LOGO_DIR / (uuid4().hex + '.' + extension)
                new_path.write_bytes(data)
                partner.logo = '/static/uploads/partners/' + new_path.name
            elif not original:
                raise ValueError('Dodaj logo partnera.')
            if original:
                source.partners.remove(original)
            destination.partners.append(partner)
            return commit(db, config, 'section-' + destination.id)
        except Exception as error:
            db.rollback()
            if new_path:
                new_path.unlink(missing_ok=True)
            if isinstance(error, ValueError):
                return render(request, db, admin, str(error), 422)
            raise

    @router.post('/sections/{section_id}/partners')
    async def add_partner(section_id: str, request: Request, name: str = Form(...), website: str = Form(''),
                          logo_scale: float = Form(1, ge=.5, le=3), sort_order: int = Form(0, ge=0, le=100000),
                          logo: UploadFile = File(...), db: Session = Depends(get_db), admin=Depends(require_superadmin)):
        config = get_partners(db)
        section = section_for(config, section_id)
        return await store_partner(request, db, admin, config, section, None, name, website, logo_scale, sort_order, section_id, logo)

    @router.post('/sections/{section_id}/partners/{partner_id}')
    async def edit_partner(section_id: str, partner_id: str, request: Request, name: str = Form(...),
                           website: str = Form(''), logo_scale: float = Form(1, ge=.5, le=3),
                           sort_order: int = Form(0, ge=0, le=100000), destination_section: str = Form(...),
                           logo: UploadFile | None = File(None), db: Session = Depends(get_db), admin=Depends(require_superadmin)):
        config = get_partners(db)
        section = section_for(config, section_id)
        return await store_partner(request, db, admin, config, section, partner_id, name, website, logo_scale,
                                   sort_order, destination_section, logo)

    @router.post('/sections/{section_id}/partners/{partner_id}/delete')
    def delete_partner(section_id: str, partner_id: str, db: Session = Depends(get_db)):
        config = get_partners(db)
        section = section_for(config, section_id)
        partner = next((item for item in section.partners if item.id == partner_id), None)
        if partner is None:
            raise HTTPException(404)
        section.partners.remove(partner)
        return commit(db, config, 'section-' + section_id)

    return router

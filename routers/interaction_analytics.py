from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from interaction_analytics import (ENABLED_KEY, PAGE_LABELS, RETENTION_DAYS, public_html_path,
                                   prune, section_label, tracking_enabled, utc_now)
from models import InteractionLink, InteractionVisit, InteractionSection, SystemSetting, FormInfo
from site_pages import PUBLIC_PAGES, page_for_path, page_visibility
from referral_access import (ACCESS_COOKIE, CONSENT_COOKIE, ReferralPopup, SETTINGS_KEY, active_link, consent_matches,
                             decode_cookie, get_popup, set_access_cookie, signed_cookie)
from templating import create_templates

templates = create_templates()
public_router = APIRouter()


class SectionSample(BaseModel):
    model_config = ConfigDict(extra='forbid')
    section_id: str = Field(min_length=1, max_length=100, pattern=r'^[a-zA-Z0-9_-]+$')
    visible_ms: int = Field(ge=0, le=86400000, strict=True)
    clicks: int = Field(default=0, ge=0, le=100000, strict=True)
    faq_opens: int = Field(default=0, ge=0, le=100000, strict=True)


class InteractionBatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    link_id: UUID
    visit_id: UUID
    path: str = Field(max_length=200)
    samples: list[SectionSample] = Field(max_length=100)

    @field_validator('path')
    @classmethod
    def valid_path(cls, value):
        if not public_html_path(value):
            raise ValueError('Nieprawidłowa strona.')
        return value

    @model_validator(mode='after')
    def unique_sections(self):
        if len({s.section_id for s in self.samples}) != len(self.samples):
            raise ValueError('Powtórzone sekcje.')
        return self


class ReferralDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    accepted: StrictBool
    link_id: UUID | None = None
    revision: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')


@public_router.post('/api/referrals/decision')
def referral_decision(request: Request, decision: ReferralDecision, db: Session = Depends(get_db)):
    origin = request.headers.get('origin')
    if origin and origin != str(request.base_url).rstrip('/'):
        raise HTTPException(403)
    link = active_link(db, decision.link_id) if decision.link_id else None
    has_access = decode_cookie(request.cookies.get(ACCESS_COOKIE), 'partner-access').get('access') is True
    if decision.accepted and link is None:
        raise HTTPException(404)
    if decision.link_id and link is None:
        raise HTTPException(404)
    if not link and not has_access:
        # A naked No request cannot mint an entitlement cookie.
        raise HTTPException(403)
    accepted = decision.accepted and request.headers.get('DNT') != '1' and request.headers.get('Sec-GPC') != '1'
    popup = get_popup(db)
    if accepted and decision.revision != popup.revision:
        raise HTTPException(409, 'Treść prośby o zgodę zmieniła się. Odśwież stronę, aby przeczytać aktualną treść.')
    from fastapi.responses import JSONResponse
    response = JSONResponse({'access': True, 'consented': accepted,
                             'tracking': bool(accepted and tracking_enabled(db))},
                            headers={'Cache-Control': 'private, no-store'})
    set_access_cookie(response, request)
    if accepted:
        response.set_cookie(CONSENT_COOKIE, signed_cookie({'link_id': link.id, 'revision': popup.revision}, 'tracking-consent'),
                            httponly=True, secure=request.url.scheme == 'https', samesite='lax', path='/')
    else:
        response.delete_cookie(CONSENT_COOKIE, path='/', secure=request.url.scheme == 'https', httponly=True, samesite='lax')
    return response


@public_router.post('/api/interactions', status_code=204)
def collect(request: Request, batch: InteractionBatch, db: Session = Depends(get_db)):
    if request.headers.get('DNT') == '1' or request.headers.get('Sec-GPC') == '1':
        return Response(status_code=204)
    origin = request.headers.get('origin')
    if origin and origin != str(request.base_url).rstrip('/'):
        raise HTTPException(403)
    if not tracking_enabled(db):
        raise HTTPException(404)
    if not consent_matches(db, request, batch.link_id):
        raise HTTPException(403)
    page = page_for_path(batch.path)
    if not page or not page_visibility(db)[page]:
        raise HTTPException(404)
    if batch.path.startswith('/forms/') and not db.query(FormInfo).filter_by(slug=batch.path.split('/')[-1], enabled=True).first():
        raise HTTPException(404)
    # Serialize updates to the same link across workers. Cumulative maxima make
    # duplicate, late and retried heartbeat/beacon requests idempotent.
    link = db.query(InteractionLink).filter_by(id=str(batch.link_id), active=True).with_for_update().first()
    if link is None:
        raise HTTPException(404)
    now = utc_now()
    prune(db)
    visit = db.get(InteractionVisit, str(batch.visit_id))
    if visit and (visit.link_id != link.id or visit.path != batch.path):
        raise HTTPException(409)
    if visit is None:
        visit = InteractionVisit(id=str(batch.visit_id), link_id=link.id, path=batch.path, created_at=now, updated_at=now)
        db.add(visit)
        db.flush()
    visit.updated_at = now
    known = {key for key, in db.query(InteractionSection.section_id).filter_by(visit_id=visit.id)}
    if len(known | {sample.section_id for sample in batch.samples}) > 100:
        raise HTTPException(422, 'Za dużo sekcji.')
    # Client durations are estimates, capped by the server-observed visit age
    # plus one heartbeat's grace; no arbitrary historic durations are accepted.
    maximum = min(86400000, int((now - visit.created_at).total_seconds() * 1000) + 15000)
    for sample in batch.samples:
        record = db.get(InteractionSection, (visit.id, sample.section_id))
        if record is None:
            record = InteractionSection(visit_id=visit.id, section_id=sample.section_id, visible_ms=0, clicks=0, faq_opens=0)
            db.add(record)
        record.visible_ms = max(record.visible_ms, min(sample.visible_ms, maximum))
        record.clicks = max(record.clicks, sample.clicks)
        record.faq_opens = max(record.faq_opens, sample.faq_opens)
    db.commit()
    return Response(status_code=204)


def build_admin_router(require_superadmin):
    router = APIRouter(prefix='/admin/analytics', dependencies=[Depends(require_superadmin)])

    def link_for(db, link_id):
        link = db.get(InteractionLink, link_id)
        if link is None:
            raise HTTPException(404)
        return link

    def remove_visits(db, link_id):
        visits = db.query(InteractionVisit.id).filter_by(link_id=link_id)
        db.query(InteractionSection).filter(InteractionSection.visit_id.in_(visits)).delete(synchronize_session=False)
        db.query(InteractionVisit).filter_by(link_id=link_id).delete(synchronize_session=False)

    @router.get('')
    def dashboard(request: Request, db: Session = Depends(get_db), admin=Depends(require_superadmin)):
        prune(db)
        db.commit()
        counts = dict(db.query(InteractionVisit.link_id, func.count()).group_by(InteractionVisit.link_id).all())
        return templates.TemplateResponse(request, 'admin/analytics.html', {
            'request': request, 'admin': admin, 'enabled': tracking_enabled(db),
            'links': db.query(InteractionLink).order_by(InteractionLink.created_at.desc()).limit(500).all(),
            'counts': counts, 'pages': PUBLIC_PAGES, 'retention_days': RETENTION_DAYS, 'popup': get_popup(db),
        })

    @router.post('/settings')
    def settings(enabled: bool = Form(False), db: Session = Depends(get_db)):
        db.merge(SystemSetting(key=ENABLED_KEY, value='true' if enabled else 'false'))
        db.commit()
        return RedirectResponse('/admin/analytics', 303)

    @router.post('/referral-settings')
    def referral_settings(title: str = Form(...), content: str = Form(...), accept_label: str = Form(...),
                          reject_label: str = Form(...), db: Session = Depends(get_db)):
        try:
            popup = ReferralPopup(title=title, content=content, accept_label=accept_label, reject_label=reject_label)
        except ValueError:
            raise HTTPException(422, 'Wypełnij treść okna i etykiety przycisków.') from None
        db.merge(SystemSetting(key=SETTINGS_KEY, value=popup.model_dump_json()))
        db.commit()
        return RedirectResponse('/admin/analytics', 303)

    @router.post('/links')
    def create(path: str = Form(...), label: str = Form('', max_length=120), db: Session = Depends(get_db)):
        if not public_html_path(path):
            raise HTTPException(422)
        if db.query(InteractionLink).count() >= 500:
            raise HTTPException(422, 'Limit 500 linków. Usuń nieużywane linki.')
        link = InteractionLink(id=str(uuid4()), label=label.strip(), path=path)
        db.add(link)
        db.commit()
        return RedirectResponse('/admin/analytics/' + link.id, 303)

    @router.get('/{link_id}')
    def report(link_id: str, request: Request, db: Session = Depends(get_db), admin=Depends(require_superadmin)):
        link = link_for(db, link_id)
        prune(db)
        db.commit()
        rows = db.query(InteractionVisit.path, InteractionSection.section_id,
                        func.sum(InteractionSection.visible_ms).label('visible_ms'),
                        func.sum(InteractionSection.clicks).label('clicks'),
                        func.sum(InteractionSection.faq_opens).label('faq_opens'),
                        func.count().label('visits')).join(InteractionSection, InteractionSection.visit_id == InteractionVisit.id).filter(
                            InteractionVisit.link_id == link.id).group_by(InteractionVisit.path, InteractionSection.section_id).order_by(
                                InteractionVisit.path, InteractionSection.section_id).all()
        rows = [dict(row._mapping, page_label=PAGE_LABELS.get(row.path, row.path), section_label=section_label(db, row.path, row.section_id)) for row in rows]
        visits = db.query(InteractionVisit).filter_by(link_id=link.id)
        return templates.TemplateResponse(request, 'admin/analytics_report.html', {
            'request': request, 'admin': admin, 'link': link, 'rows': rows,
            'url': str(request.base_url).rstrip('/') + link.path + '?ref=' + link.id,
            'visit_count': visits.count(), 'recent_visits': visits.order_by(InteractionVisit.created_at.desc()).limit(100).all(),
            'total_ms': sum(row['visible_ms'] for row in rows if row['section_id'] == 'page'),
        })

    @router.post('/{link_id}/toggle')
    def toggle(link_id: str, db: Session = Depends(get_db)):
        link = link_for(db, link_id)
        link.active = not link.active
        db.commit()
        return RedirectResponse('/admin/analytics/' + link.id, 303)

    @router.post('/{link_id}/clear')
    def clear(link_id: str, db: Session = Depends(get_db)):
        link_for(db, link_id)
        remove_visits(db, link_id)
        db.commit()
        return RedirectResponse('/admin/analytics/' + link_id, 303)

    @router.post('/{link_id}/delete')
    def delete(link_id: str, db: Session = Depends(get_db)):
        link = link_for(db, link_id)
        remove_visits(db, link_id)
        db.delete(link)
        db.commit()
        return RedirectResponse('/admin/analytics', 303)

    return router

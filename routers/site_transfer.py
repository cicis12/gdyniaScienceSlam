from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
import re
import time

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from database import get_db
from models import GalleryPhoto, TeamMember
from site_transfer import MAX_ARCHIVE_BYTES, export_bundle, inspect_bundle, apply_bundle, check_form_conflicts
from templating import create_templates

STAGING_DIR = Path(__file__).resolve().parents[1] / 'uploads/config-previews'
templates = create_templates()


def build_router(require_superadmin, secret_key):
    router = APIRouter(prefix='/admin/transfer', dependencies=[Depends(require_superadmin)])

    def render(request, admin, error=None, status_code=200, **context):
        return templates.TemplateResponse('admin/transfer.html', {
            'request': request, 'admin': admin, 'error': error, **context,
        }, status_code=status_code)

    @router.get('')
    def dashboard(request: Request, admin=Depends(require_superadmin)):
        return render(request, admin)

    @router.get('/export')
    def download(request: Request, db: Session = Depends(get_db), admin=Depends(require_superadmin)):
        try:
            data = export_bundle(db)
        except (ValueError, OSError) as exc:
            return render(request, admin, error='Eksport nie powiódł się: ' + str(exc)[:400], status_code=422)
        return Response(data, media_type='application/zip', headers={
            'Content-Disposition': f'attachment; filename="gss-config-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.zip"',
            'Cache-Control': 'no-store',
        })

    @router.post('/preview')
    async def preview(request: Request, bundle: UploadFile = File(...), scope: str = Form('gallery'),
                      db: Session = Depends(get_db), admin=Depends(require_superadmin)):
        try:
            if scope not in {'gallery', 'all'}:
                raise ValueError('Wybierz zakres importu.')
            data = await bundle.read(MAX_ARCHIVE_BYTES + 1)
            config, media = inspect_bundle(data)
            if scope == 'all':
                check_form_conflicts(db, config)
            STAGING_DIR.mkdir(parents=True, exist_ok=True)
            for old in STAGING_DIR.glob('*.zip'):
                if re.fullmatch(r'[a-f0-9]{32}\.zip', old.name) and old.stat().st_mtime < time.time() - 3600:
                    old.unlink(missing_ok=True)
            filename = uuid4().hex + '.zip'
            (STAGING_DIR / filename).write_bytes(data)
            token = jwt.encode({'purpose': 'site-config-import', 'admin_id': admin.id, 'file': filename,
                                'digest': sha256(data).hexdigest(), 'scope': scope,
                                'exp': datetime.now(timezone.utc) + timedelta(minutes=30)}, secret_key, algorithm='HS256')
            return render(request, admin, preview=config, token=token, scope=scope, media_count=len(media),
                          current_photos=db.query(GalleryPhoto).count(), current_team=db.query(TeamMember).count())
        except ValueError as exc:
            return render(request, admin, error='Nie można zaimportować pakietu: ' + str(exc)[:400], status_code=422)

    @router.post('/apply')
    def apply(request: Request, token: str = Form(...), db: Session = Depends(get_db), admin=Depends(require_superadmin)):
        claimed = None
        try:
            claims = jwt.decode(token, secret_key, algorithms=['HS256'])
            if claims.get('purpose') != 'site-config-import' or claims.get('admin_id') != admin.id or not re.fullmatch(r'[a-f0-9]{32}\.zip', claims.get('file', '')):
                raise ValueError('Nieprawidłowy podgląd importu.')
            path = STAGING_DIR / claims['file']
            if not path.is_file() or path.stat().st_size > MAX_ARCHIVE_BYTES:
                raise ValueError('Podgląd wygasł lub został już użyty. Wgraj pakiet ponownie.')
            # Claim once across workers, so double-clicking cannot apply the same package twice.
            candidate = path.with_suffix('.processing')
            try:
                path.rename(candidate)
            except FileNotFoundError:
                raise ValueError('Ten import jest już wykonywany lub został zakończony.') from None
            claimed = candidate
            data = claimed.read_bytes()
            if sha256(data).hexdigest() != claims['digest']:
                raise ValueError('Pakiet zmienił się od utworzenia podglądu.')
            config, media = inspect_bundle(data)
            apply_bundle(db, config, media, claims['scope'])
        except (JWTError, ValueError, KeyError) as exc:
            return render(request, admin, error='Import nie został wykonany. Wgraj pakiet ponownie. ' + str(exc)[:300], status_code=422)
        finally:
            if claimed:
                claimed.unlink(missing_ok=True)
        return RedirectResponse('/admin/transfer?imported=1', 303)

    return router

from fastapi import FastAPI, Form, File, UploadFile, Depends, Request, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response, PlainTextResponse
from fastapi.staticfiles import StaticFiles 
from templating import create_templates
from pathlib import Path
import json
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from database import SessionLocal, engine, Base, get_db
import shutil, os
from models import AdminUser, Voter, Vote, SystemSetting, FormInfo, FormVersion, FormSubmission, TeamMember, GalleryPhoto
from gallery import get_featured_video
from site_pages import page_visibility, page_for_path
from system_settings import load_public_settings
from partner_content import get_partners
from home_images import get_home_images
from document_content import get_documents, document_path
from team_theme import get_team_palette, team_details_enabled
from starlette.concurrency import run_in_threadpool
import uuid
from datetime import date
from video import save_video
from sqlalchemy.exc import IntegrityError
from security import verify_password
from admin_sessions import create_admin_session, session_admin, check_csrf, fingerprint
from models import AdminSession
from datetime import datetime, timedelta
from dotenv import load_dotenv
from jose import jwt
from mail import send_confirmation_email, send_email
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from operator import attrgetter
from jose import JWTError
from rapidfuzz import fuzz
from urllib.parse import urlparse, parse_qs, quote
from form_uploads import attachment_path, FILE_TYPES
from pydantic import BaseModel


#set up needed variables
app = FastAPI()
app.mount("/static",StaticFiles(directory="static"), name="static")
BASE_DIR = Path(__file__).resolve().parent

templates=create_templates()

#rate limiter
rate_limit_storage_uri = os.getenv("RATE_LIMIT_STORAGE_URI", "memory://")
limiter = Limiter(key_func=get_remote_address, storage_uri=rate_limit_storage_uri)

app.state.limiter = limiter

from routers.admin_forms import router as admin_router
from routers.forms import router as form_router

app.include_router(form_router)


def load_public_context():
    with SessionLocal() as db:
        return page_visibility(db), load_public_settings(db)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"detail": "Zbyt dużo zapytań. Spróbuj ponownie później."}, headers={"Retry-After": "60"})


#serve pages (@app.get)
@app.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "client/index.html", {
        "request": request,
        "header_title": "Gdynia Science Slam",
        "page_name": "home",
        "carousel_partners": get_partners(db).carousel_partners,
        "home_images": get_home_images(db),
        "event_datetime": get_setting(db, "event_datetime", ""),
        "event_date_only": get_setting(db, "event_date_only", "false") == "true",
        "members": db.query(TeamMember).order_by(TeamMember.id).all(),
    })

@app.get("/team")
def team(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "client/team.html", {
        "request": request, "header_title": "Zespół - Gdynia Science Slam", "page_name": "team",
        "members": db.query(TeamMember).order_by(TeamMember.id).all(),
        "team_palette": get_team_palette(db),
        "team_details_enabled": team_details_enabled(db),
    })

@app.get("/registration")
def registration(request: Request, db: Session = Depends(get_db)):
    active_forms = db.query(FormInfo).filter(FormInfo.enabled.is_(True)).order_by(FormInfo.name.asc()).all()
    setting = db.get(SystemSetting, "registration_form_ids")
    try:
        selected_ids = [int(value) for value in (setting.value if setting else "").split(",") if value][:3]
    except ValueError:
        selected_ids = []

    active_forms_by_id = {form.id: form for form in active_forms}
    creator_forms = []
    selected_form_ids = set()
    for form_id in selected_ids:
        form = active_forms_by_id.get(form_id)
        if not form:
            continue
        version = db.query(FormVersion).filter(
            FormVersion.id == form.cur_version_id,
            FormVersion.form_id == form.id,
        ).first()
        if version:
            selected_form_ids.add(form.id)
            creator_forms.append({
                "id": form.id,
                "name": version.display_name,
                "slug": form.slug,
                "description": version.description,
                "version_id": version.id,
                "svg": version.definition.get("svg"),
                "fields": version.definition.get("fields", []),
            })

    standalone_forms = []
    show_other_forms = get_setting(db, 'registration_show_other_forms', 'false') == 'true'
    for form in active_forms if show_other_forms else []:
        if form.id in selected_form_ids:
            continue
        version = db.query(FormVersion).filter(
            FormVersion.id == form.cur_version_id,
            FormVersion.form_id == form.id,
        ).first()
        if version:
            standalone_forms.append({
                "name": version.display_name,
                "slug": form.slug,
                "description": version.description,
            })

    return templates.TemplateResponse(request, "client/registration.html", {
        "request": request,
        "header_title": "Rejestracja - Gdynia Science Slam",
        "page_name": "registration",
        "creator_forms": creator_forms,
        "standalone_forms": standalone_forms,
    })

@app.get("/about")
def about(request: Request, db: Session = Depends(get_db)):
    from about_content import get_timeline
    return templates.TemplateResponse(request, "client/about.html", {"request": request, "header_title": "O Nas - Gdynia Science Slam", "page_name":"about", "entries": get_timeline(db)})

@app.get("/previous_editions")
def previous(request: Request, db: Session = Depends(get_db)):
    photos = db.query(GalleryPhoto).order_by(GalleryPhoto.year.desc(), GalleryPhoto.sort_order, GalleryPhoto.id).all()
    editions = {}
    for photo in photos:
        editions.setdefault(photo.year, []).append(photo)
    return templates.TemplateResponse(request, "client/previous.html", {
        "request": request, "header_title": "Poprzednie edycje - Gdynia Science Slam", "page_name": "previous_editions",
        "editions": editions, "photo_count": len(photos), "video": get_featured_video(db),
    })

@app.get("/partners")
def partners(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "client/partners.html", {"request": request, "header_title": "Partnerzy - Gdynia Science Slam", "page_name":"partners", "partner_config": get_partners(db)})

@app.get("/documents")
def documents(request: Request, db: Session = Depends(get_db)):
    editions = {}
    for document in get_documents(db):
        if document.enabled:
            editions.setdefault(document.year, []).append(document)
    return templates.TemplateResponse(request, "client/documents.html", {
        "request": request, "header_title": "Dokumenty - Gdynia Science Slam", "page_name": "documents",
        "document_editions": editions,
    })


@app.get("/documents/download/{document_id}")
def download_document(document_id: str, db: Session = Depends(get_db)):
    document = next((item for item in get_documents(db) if item.id == document_id and item.enabled), None)
    if document is None:
        raise HTTPException(404)
    try:
        path = document_path(document)
    except ValueError:
        raise HTTPException(404) from None
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, filename=document.filename, media_type="application/pdf",
                        content_disposition_type="attachment", headers={"X-Content-Type-Options": "nosniff"})

# @app.get("/groups")
# def groups(request: Request):
#     return templates.TemplateResponse("client/partners.html", {"request": request, "header_title": "Rejestracja - Gdynia Science Slam", "page_name":"groups"})

@app.get("/topics")
def topics(request: Request):
    return templates.TemplateResponse(request, "client/topics.html", {"request": request, "header_title": "Tematy - Gdynia Science Slam", "page_name":"topics"})



#ADMIN PAGES
load_dotenv("SECRET_KEY.env")
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is not set")
ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 240



def get_current_admin(request: Request, db: Session = Depends(get_db)):
    return session_admin(db, request.cookies.get("admin_session"))


def require_superadmin(admin: AdminUser = Depends(get_current_admin)):
    if not (admin.is_superadmin or admin.is_sysadmin):
        raise HTTPException(status_code=403, detail="Superadmin only")
    return admin


def require_sysadmin(admin: AdminUser = Depends(get_current_admin)):
    if not admin.is_sysadmin:
        raise HTTPException(403, 'Tylko administrator systemowy może zarządzać kontami.')
    return admin


from routers.admin_accounts import build_router as build_accounts_router
app.include_router(build_accounts_router(require_sysadmin))
from routers.site_content import build_router
app.include_router(build_router(require_superadmin))
from routers.gallery_admin import build_router as build_gallery_router
from routers.about_admin import build_router as build_about_router
from routers.site_transfer import build_router as build_transfer_router
app.include_router(build_gallery_router(require_superadmin))
app.include_router(build_about_router(require_superadmin))
from routers.partners_admin import build_router as build_partners_router
app.include_router(build_partners_router(require_superadmin))
from routers.documents_admin import build_router as build_documents_router
app.include_router(build_documents_router(require_superadmin))
app.include_router(build_transfer_router(require_superadmin, SECRET_KEY))


def load_admin_context(request):
    with SessionLocal() as db:
        return get_current_admin(request, db)


@app.get("/admin/form-submissions")
def admin_form_submissions(
    request: Request,
    form_id: int | None = None,
    page: int = 1,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    forms = db.query(FormInfo).order_by(FormInfo.name.asc()).all()
    selected_form = db.get(FormInfo, form_id) if form_id is not None else None
    submissions = []
    page = max(1, page)
    total = 0

    if selected_form:
        total = db.query(FormSubmission).filter_by(form_id=selected_form.id).count()
        saved_submissions = (
            db.query(FormSubmission)
            .filter(FormSubmission.form_id == selected_form.id)
            .order_by(FormSubmission.submitted_at.desc(), FormSubmission.id.desc())
            .offset((page - 1) * 50).limit(50)
            .all()
        )
        versions = {
            version.id: version
            for version in db.query(FormVersion)
            .filter(FormVersion.form_id == selected_form.id)
            .all()
        }

        for submission in saved_submissions:
            version = versions.get(submission.form_version_id)
            labels = {}
            if version:
                for field in version.definition.get("fields", []):
                    if field.get("name"):
                        labels[field["name"]] = field.get("question") or field["name"]
                    if field.get("name2"):
                        labels[field["name2"]] = field.get("question2") or field["name2"]

            file_fields = {f['name'] for f in version.definition.get('fields', []) if f.get('type') == 'file'} if version else set()
            answers = [
                {
                    "key": key,
                    "label": labels.get(key, key),
                    "attachment": value if key in file_fields and isinstance(value, dict) and value.get('kind') == 'attachment' else None,
                    "upload_url": f"/admin/uploads/{submission.id}/{quote(key, safe='')}",
                    "value": (
                        "—" if value in (None, "") else
                        ("Tak" if value else "Nie") if isinstance(value, bool) else
                        json.dumps(value, ensure_ascii=False, indent=2)
                        if isinstance(value, (dict, list)) else str(value)
                    ),
                }
                for key, value in (submission.data or {}).items()
            ]
            submissions.append({
                "id": submission.id,
                "submitted_at": submission.submitted_at,
                "version_num": version.version_num if version else None,
                "answers": answers,
            })

    return templates.TemplateResponse(request, "admin_form_submissions.html", {
        "request": request,
        "admin": admin,
        "forms": forms,
        "selected_form": selected_form,
        "submissions": submissions, "page": page, "total": total, "has_next": page * 50 < total,
    })

@app.get('/admin/uploads/{submission_id}/{field_name}')
def download_submission_file(submission_id: int, field_name: str, download: bool = False,
                             admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    submission = db.get(FormSubmission, submission_id)
    record = submission.data.get(field_name) if submission else None
    if not isinstance(record, dict) or record.get('kind') != 'attachment':
        raise HTTPException(404)
    path = attachment_path(record)
    media_type = FILE_TYPES[path.suffix]
    inline = media_type.startswith('video/') and not download
    return FileResponse(path, media_type=media_type, filename=record.get('filename', path.name),
                        content_disposition_type='inline' if inline else 'attachment',
                        headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store',
                                 'Content-Security-Policy': "default-src 'none'; sandbox"})


@app.exception_handler(HTTPException)
async def auth_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401 and request.scope["path"].startswith("/admin"):
        return RedirectResponse("/admin/login")
    return JSONResponse(status_code=exc.status_code, content={"detail":exc.detail})

# EMAIL SENDER
def get_emails_from_table(
    table: str,
    db: Session
    ):
    TABLE_MAP = {
        "contestants": Contestant,
        "viewers": Viewer,
        "volunteers": Volunteer,
        "groups": Group,
    }

    model=TABLE_MAP.get(table)

    if not model:
        return []

    results = db.query(model.email).all()

    return [r[0] for r in results if r[0]]

@app.get("/admin/emailsender")
def admin_email_sender(
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
):
    if not (admin.is_superadmin or admin.is_sysadmin):
        raise HTTPException(
            status_code=403,
            detail="Superadmin access required."
        )
    return templates.TemplateResponse(request, "sendMails.html", {"request": request, "admin": admin})

@app.post("/admin/send-email")
async def sendemailform(
    admin: AdminUser = Depends(require_superadmin),
    table: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
    mode: str = Form(...),
    test_email: str = Form(None),
    db: Session = Depends(get_db),
):

    if mode == "test":
        recipients = [test_email]

    else:
        # get emails from DB table
        recipients = get_emails_from_table(table,db)

    for email in recipients:
        send_email(
            to_email=email,
            content=body,
            subject=subject,
        )

    return RedirectResponse(
        url="/admin/emailsender?success=1",
        status_code=303
    )

@app.post("/admin/send-email/preview")
async def preview_email(
    request: Request,
    admin: AdminUser = Depends(require_superadmin),
    table: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
    mode: str = Form(...),
    test_email: str = Form(None),
):
    return templates.TemplateResponse(
        request, "email_confirm.html",
        {
            "request": request,
            "table": table,
            "subject": subject,
            "body": body,
            "mode": mode,
            "test_email": test_email,
        }
    )

@app.get("/admin/dashboard")
def admin_dashboard(
    request: Request,
    admin: AdminUser = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    forms = db.query(FormInfo).order_by(FormInfo.name.asc()).all()
    submission_counts = {
        form.id: db.query(func.count(FormSubmission.id))
        .filter(FormSubmission.form_id == form.id)
        .scalar()
        for form in forms
    }
    return templates.TemplateResponse(
        request, "admin_dashboard_home.html",
        {
            "request": request,
            "admin": admin,
            "forms": forms,
            "submission_counts": submission_counts,
        },
    )

@app.post("/admin/toggle-favourite/{item_id}")
def toggle_favourite(
    item_id: int,
    tab: str = "contestant",
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    model = {
        "contestant": Contestant,
        "viewer": Viewer,
        "volunteer": Volunteer
    }.get(tab)

    if not model:
        return RedirectResponse("/admin/dashboard", status_code=303)
    
    item = db.query(model).get(item_id)
    item.favourite = not item.favourite
    db.commit()
    return RedirectResponse(f"/admin/dashboard?tab={tab}", status_code=303)

@app.post("/admin/toggle-hidden/{item_id}")
def toggle_hidden(
    request: Request,
    item_id: int,
    redirect_url: str = Form(...),
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):

    parsed = urlparse(redirect_url)
    tab = parse_qs(parsed.query).get("tab", ["viewer"])[0]

    model = {
        "contestant": Contestant,
        "viewer": Viewer,
        "volunteer": Volunteer,
        "group": Group,
    }.get(tab)

    if not model:
        return RedirectResponse("/admin/dashboard", status_code=303)
    
    item = db.get(model,item_id)
    item.hidden = not item.hidden
    db.commit()

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return Response(status_code=200)

    return RedirectResponse(redirect_url, status_code=303)

@app.post("/admin/group/{group_id}/add-email")
def add_email(
    group_id: int,
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    group = db.get(Group, group_id)
    if not group:
        return JSONResponse(status_code=404, content={"ok": False, "error": "Nie znaleziono grupy."})

    group.number_of_added_emails += 1
    new_voter = Voter(
        email = email.lower().strip(),
    )
    try:
        db.add(new_voter)
        db.commit()
        db.refresh(new_voter)
        background_tasks.add_task(
            send_confirmation_email,
            new_voter.email,
            "",
            "widza"
        )
    except IntegrityError as e:
        db.rollback()
        return JSONResponse(status_code=400, content={"ok": False, "error": "Ten adres E-mail jest już zarejestrowany"})

    return {"ok": True, "new_count": group.number_of_added_emails}

@app.get("/admin", include_in_schema=False)
@app.get("/admin/", include_in_schema=False)
def admin_entry(request: Request, db: Session = Depends(get_db)):
    try:
        admin = get_current_admin(request, db)
    except HTTPException as error:
        if error.status_code != 401:
            raise
        return RedirectResponse("/admin/login", status_code=303)
    destination = "/admin/dashboard" if (admin.is_superadmin or admin.is_sysadmin) else "/admin/form-submissions"
    return RedirectResponse(destination, status_code=303)


@app.get("/admin/login")
def adminloginpage(request: Request):
    return templates.TemplateResponse(
        request, "admin_login.html",
        {"request": request}
    )


@app.post("/adminLogin", response_class=HTMLResponse)
@limiter.limit("5/minute")
async def admin_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),

    db: Session = Depends(get_db)
):
    admin = db.query(AdminUser).filter(
        AdminUser.username == username
    ).first()
    
    if not admin or not admin.is_active or not verify_password(password,admin.password_hash):
        return templates.TemplateResponse(
            request, "admin_login.html",
            {
                "request": request,
                "error": "Błedna nazwa użytkownika lub hasło."
            }
        )
    
    token = create_admin_session(db, admin)

    landing_page = "/admin/dashboard" if (admin.is_superadmin or admin.is_sysadmin) else "/admin/form-submissions"
    response = RedirectResponse(landing_page, status_code=303)

    response.set_cookie(
        key="admin_session",
        value=token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        expires=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

    return response

@app.post("/admin/logout")
def admin_logout(request: Request, csrf: str = Form(...), db: Session = Depends(get_db)):
    check_csrf(request, csrf)
    token = request.cookies.get('admin_session', '')
    db.query(AdminSession).filter_by(token_hash=fingerprint(token)).delete()
    db.commit()
    response = RedirectResponse('/admin/login', status_code=303)
    response.delete_cookie('admin_session', secure=True, httponly=True, samesite='strict')
    response.headers['Cache-Control'] = 'no-store'
    return response


CONTESTANT_VID_DIR = BASE_DIR / "uploads" / "filmikuczestnik"

@app.get("/admin/video/{filename}")
def get_video(filename: str, admin: AdminUser = Depends(get_current_admin)):
    file_path = (CONTESTANT_VID_DIR / filename).resolve()

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    if CONTESTANT_VID_DIR not in file_path.parents:
        raise HTTPException(status_code=403,detail="Invalid path")

    return FileResponse(file_path)


# VOTING
from vote import create_voter_token, get_current_voter, decode_voter, VOTER_TOKEN_EXPIRE_SECONDS
@app.post("/vote/login")
def vote_login(
    email: str = Form(...),
    db: Session = Depends(get_db)
):
    voter = db.query(Voter).filter(Voter.email == email.lower().strip()).first()

    if not voter:
        return Response("Email not registered", status_code=404)

    token = create_voter_token(voter.id, voter.email)

    response = RedirectResponse("/vote", status_code=303)

    response.set_cookie(
        key="voter_session",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=VOTER_TOKEN_EXPIRE_SECONDS,
        expires=VOTER_TOKEN_EXPIRE_SECONDS
    )

    return response

@app.get("/vote")
def vote_page(
    request: Request,
    db: Session = Depends(get_db)
):
    voting_enabled = get_setting(db, "voting_enabled", "true") == "true"

    
    voter = decode_voter(request,db)

    if not voting_enabled:
        return templates.TemplateResponse(request, "vote_closed.html",{"request": request, "voter": voter})

    votes_left = 0
    voted_choices = set()
    if voter:
        used = db.query(Vote).filter(Vote.voter_id == voter.id).count()
        votes_left = 3 - used
        voted_choices = {
        v.choice
        for v in db.query(Vote).filter(Vote.voter_id == voter.id).all()
    }

    CONTESTANTS=[
        {"id": 1, "name": "Laura Grafińska", "topic": "Dlaczego mężczyzna pomylił żonę z kapeluszem?", "img": "/static/assets/images/contestants/47 Laura.webp"},
        {"id": 2, "name": "Wojciech Kubik", "topic": "Dlaczego jedne dźwięki brzmią dobrze, a inne nie?", "img": "/static/assets/images/contestants/48 Wojciech.webp"},
        {"id": 3, "name": "Gabriela Żuprańska", "topic": "Harmonia mózgu", "img": "/static/assets/images/contestants/49 Gabriela.webp"},
        {"id": 4, "name": "Krzysztof Florek", "topic": "Badania próbek konsumenckich a geopolityka", "img": "/static/assets/images/contestants/50 Krzysztof.webp"},
        {"id": 5, "name": "Natalia Monkiewicz", "topic": "Dlaczego twój układ immunologiczny się nie buntuje - i co by się stało gdyby to zrobił?", "img": "/static/assets/images/contestants/51 Natalia.webp"},
        {"id": 6, "name": "Hanna Grzybek", "topic": "Co łączy śmierć ze śmiechu i szalone krowy?", "img": "/static/assets/images/contestants/52 Hanna.webp"},
        {"id": 7, "name": "Stanisław Matuszewski", "topic": "Prąd elektryczny jako ruch cząsteczek elementarnych - czyli wykorzystywanie zjawisk kwantowych w elektrotechnice", "img": "/static/assets/images/contestants/53 Stanisław.webp"},
        {"id": 8, "name": "Dorota Słowi", "topic": "Psychoza AI - czy chatbot może być Twoim przyjacielem?", "img": "/static/assets/images/contestants/54 Dorota .webp"},
        {"id": 9, "name": "Małgorzata Narożnik", "topic": "InfecSense - platforma niewczesnych opatrunków aktywnych", "img": "/static/assets/images/contestants/55 Małgorzata.webp"},
        {"id": 10, "name": "Malina Graczyk", "topic": "Dobranoc czyli dzień dobry - Selekcja pamięci podczas snu", "img": "/static/assets/images/contestants/56 Malina.webp"},
        {"id": 11, "name": "Lilia Hrynkiewicz", "topic": "Jak księżyc zaprowadzi nas na Marsa?", "img": "/static/assets/images/contestants/57 Lilia.webp"},
    ]

    

    return templates.TemplateResponse(request, "vote.html", {
        "request": request,
        "voter": voter,
        "votes_left": votes_left,
        "contestants": CONTESTANTS,
        "voted_choices": list(voted_choices)
    })


class VoteRequest(BaseModel):
    votes: list[int]


@app.post("/vote/submit")
def submit_votes(
    data: VoteRequest,
    voter: Voter = Depends(get_current_voter),
    db: Session = Depends(get_db)
):

    if get_setting(db, "voting_enabled", "true") != "true":
        raise HTTPException(403, "Voting is closed")

    existing_votes = db.query(Vote).filter(Vote.voter_id == voter.id).all()

    existing_choices = {v.choice for v in existing_votes}

    # 1. prevent duplicates in same request
    if len(data.votes) != len(set(data.votes)):
        raise HTTPException(400, "Duplicate votes in request")

    # 2. prevent voting twice for same contestant
    duplicates = set(data.votes) & existing_choices
    if duplicates:
        raise HTTPException(
            400,
            f"Already voted for: {list(duplicates)}"
        )

    # 3. enforce max limit
    remaining = 3 - len(existing_votes)
    if len(data.votes) > remaining:
        raise HTTPException(400, "Vote limit exceeded")

    # 4. insert votes
    for choice in data.votes:
        db.add(Vote(
            voter_id=voter.id,
            choice=choice
        ))

    db.commit()

    remaining = 3 - db.query(Vote).filter(Vote.voter_id == voter.id).count()
    return {
        "ok": True,
        "votes_left": remaining
    }

@app.post("/admin/toggle-voting")
def toggle_voting(
    request: Request,
    redirect_url: str = Form("/admin/dashboard?tab=voting"),
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    setting = db.get(SystemSetting, "voting_enabled")

    if not setting:
        setting = SystemSetting(key="voting_enabled", value="true")
        db.add(setting)
    else:
        setting.value = "false" if setting.value == "true" else "true"

    db.commit()

    # AJAX support (same pattern as toggle_hidden)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return Response(status_code=200)

    return RedirectResponse(redirect_url, status_code=303)

def get_setting(db: Session, key: str, default="false"):
    s = db.get(SystemSetting, key)
    return s.value if s else default


app.include_router(admin_router, dependencies=[Depends(require_superadmin)])


@app.post("/admin/event-settings")
def save_event_settings(
    event_datetime: str = Form(""),
    event_date_only: bool = Form(False),
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_superadmin),
):
    event_datetime = event_datetime.strip()
    if event_datetime:
        try:
            parsed_event_datetime = datetime.fromisoformat(event_datetime)
        except ValueError:
            raise HTTPException(status_code=400, detail="Nieprawidłowa data wydarzenia.")
        event_datetime = parsed_event_datetime.strftime("%Y-%m-%dT%H:%M")

    setting = db.get(SystemSetting, "event_datetime")
    if setting:
        setting.value = event_datetime
    else:
        setting = SystemSetting(key="event_datetime", value=event_datetime)
        db.add(setting)
    display_setting = db.get(SystemSetting, "event_date_only")
    if display_setting:
        display_setting.value = "true" if event_date_only else "false"
    else:
        db.add(SystemSetting(key="event_date_only", value="true" if event_date_only else "false"))
    db.commit()
    return RedirectResponse("/admin/content?saved=1#event", status_code=303)


@app.get("/admin/manage_votes")
def manage_votes(
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_superadmin),
):
    voting_enabled = get_setting(db, "voting_enabled", "false") == "true"
    total_votes = db.query(Vote).count()

    raw_results = (
        db.query(Vote.choice, func.count(Vote.id))
        .group_by(Vote.choice)
        .all()
    )

    results_map = {choice: count for choice, count in raw_results}

    contestants = [
        {"id": 1, "name": "Laura Grafińska"},
        {"id": 2, "name": "Wojciech Kubik"},
        {"id": 3, "name": "Gabriela Żuprańska"},
        {"id": 4, "name": "Krzysztof Florek"},
        {"id": 5, "name": "Natalia Monkiewicz"},
        {"id": 6, "name": "Hanna Grzybek"},
        {"id": 7, "name": "Stanisław Matuszewski"},
        {"id": 8, "name": "Dorota Słowi"},
        {"id": 9, "name": "Małgorzata Narożnik"},
        {"id": 10, "name": "Malina Graczyk"},
        {"id": 11, "name": "Lilia Hrynkiewicz"},
    ]

    for c in contestants:
        c["votes"] = results_map.get(c["id"], 0)

    return templates.TemplateResponse(request, "admin_manage_votes.html", {
        "request": request,
        "admin": admin,
        "voting_enabled": voting_enabled,
        "contestants": contestants,
        "total_votes": total_votes
    })


@app.get("/admin/voters/bulk-preview")
def preview_bulk_voters(
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_superadmin),
):
    viewers = (
        db.query(Viewer)
        .all()
    )

    emails = {v.email.lower().strip() for v in viewers}

    existing = {
        email for (email,) in db.query(Voter.email).all()
    }

    to_create = emails - existing

    return {
        "eligible_viewers": len(emails),
        "already_voters": len(emails - to_create),
        "new_voters": len(to_create),
    }



@app.post("/admin/voters/bulk-create")
def bulk_create_voters(
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_superadmin),
):
    viewers = (
        db.query(Viewer)
        .all()
    )

    emails = {v.email.lower().strip() for v in viewers}

    existing = {
        email for (email,) in db.query(Voter.email).all()
    }

    new_emails = emails - existing

    if not new_emails:
        return {"ok": True, "created": 0}

    new_voters = [
        Voter(email=email)
        for email in new_emails
    ]

    db.add_all(new_voters)
    db.commit()

    # AJAX support like your existing system
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return {"ok": True, "created": len(new_voters)}

    return RedirectResponse("/admin/manage_votes", status_code=303)


@app.post("/admin/voters/filter-by-hidden-viewers")
def filter_voters_by_hidden_viewers(
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_superadmin),
):
    viewers = db.query(Viewer).all()

    viewer_map = {
        v.email.lower().strip(): v.hidden
        for v in viewers
    }

    voters = db.query(Voter).all()

    to_delete = []

    for voter in voters:
        email = voter.email.lower().strip()

        # no matching viewer OR viewer not hidden → delete
        if email not in viewer_map or viewer_map[email] != True:
            to_delete.append(voter)

    deleted_count = len(to_delete)

    for v in to_delete:
        db.delete(v)

    db.commit()

    return {
        "ok": True,
        "deleted": deleted_count,
        "remaining": db.query(Voter).count()
    }


@app.get("/admin/voters/filter-preview")
def filter_preview(
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_superadmin),
):
    viewers = db.query(Viewer).all()

    viewer_map = {
        v.email.lower().strip(): v.hidden
        for v in viewers
    }

    voters = db.query(Voter).all()

    to_delete = 0
    keep = 0

    for voter in voters:
        email = voter.email.lower().strip()

        if email not in viewer_map or viewer_map[email] != True:
            to_delete += 1
        else:
            keep += 1

    return {
        "total_voters": len(voters),
        "to_delete": to_delete,
        "keep": keep
    }

@app.post("/admin/votes/delete-all")
def delete_all_votes(
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_superadmin),
):
    deleted = db.query(Vote).delete()  # bulk delete, fast

    db.commit()

    # AJAX support (consistent with your system)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return {"ok": True, "deleted": deleted}

    return RedirectResponse("/admin/manage_votes", status_code=303)


# Run body/rate checks before route parsing and database middleware.
from http_middleware import PublicContextMiddleware, AdminAccessMiddleware
from request_limits import RequestLimitsMiddleware
app.add_middleware(PublicContextMiddleware, load_context=load_public_context, templates=templates)
app.add_middleware(AdminAccessMiddleware, load_admin=load_admin_context)
app.add_middleware(RequestLimitsMiddleware)

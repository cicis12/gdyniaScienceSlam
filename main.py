from fastapi import FastAPI, Form, File, UploadFile, Depends, Request, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles 
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from database import SessionLocal, engine, Base, get_db
import shutil, os
from models import Viewer, Contestant, Volunteer, AdminUser, Voter, Vote, Group
import uuid
from datetime import date
from video import save_video
from sqlalchemy.exc import IntegrityError
from security import verify_password
from datetime import datetime, timedelta
from dotenv import load_dotenv
from jose import jwt
from mail import send_confirmation_email
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from operator import attrgetter
from jose import JWTError
from rapidfuzz import fuzz
from urllib.parse import urlparse, parse_qs


#set up needed variables
app = FastAPI()
app.mount("/static",StaticFiles(directory="static"), name="static")
BASE_DIR = Path(__file__).resolve().parent


#rate limiter
limiter = Limiter(key_func=get_remote_address, storage_uri="redis://localhost:6379")

app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    raise HTTPException(status_code=429, detail="Zbyt dużo zapytań. Spróbuj ponownie później")


#serve pages (@app.get)
@app.get("/", response_class=FileResponse)
def home():
    return BASE_DIR/ "index.html"

@app.get("/team", response_class=FileResponse)
def team():
    return BASE_DIR/"team.html"

@app.get("/registration", response_class=FileResponse)
def form():
    return BASE_DIR/"registration.html"

@app.get("/about", response_class=FileResponse)
def about():
    return BASE_DIR/"about.html"

@app.get("/previous_editions", response_class=FileResponse)
def prev():
    return BASE_DIR/"previous.html"

@app.get("/partners", response_class=FileResponse)
def partners():
    return BASE_DIR/"partners.html"

@app.get("/documents", response_class=FileResponse)
def docs():
    return BASE_DIR/"documents.html"

@app.get("/groups", response_class=FileResponse)
def groups():
    return BASE_DIR/"groups.html"

@app.get("/plan", response_class=FileResponse)
def groups():
    return BASE_DIR/"plan.html"

# Handle Post (@app.post)
# @app.post("/contestantForm")
# @limiter.limit("10/minute")
# async def handle_contestantform(
#     request: Request,
#     background_tasks: BackgroundTasks,
#     name: str = Form(...),
#     surname: str = Form(...),
#     email: str = Form(...),
#     phone: str = Form(...),
#     school: str = Form(...),
#     class_and_profile: str = Form(...),
#     city: str = Form(...),
#     birthdate: date = Form(...),

#     supervisor_name: str = Form(...),
#     supervisor_surname: str = Form(...),
#     supervisor_info: str = Form(...),

#     previous_accomplishments: str | None = Form(None),
#     about: str = Form(...),
#     interests: str = Form(...),
#     contributions: str = Form(...),
#     inspiration: str = Form(...),

#     topic: str = Form(...),
#     whytopic: str = Form(...),
#     whyinteresting: str = Form(...),
#     experience: str = Form(...),
#     ways_of_grabing_interest: str = Form(...),

#     video: UploadFile | None = File(None),
#     rules_accepted: bool = Form(...),
#     privacy_policy_accepted: bool = Form(...),
#     db: Session = Depends(get_db),
# ):
#     video_file_path = None
#     if video and video.filename:
#         if video.size > 0:
#             video_file_path = await save_video(video)
    
#     new_contestant = Contestant(
#         name=name.strip(),
#         surname=surname.strip(),
#         email=email.lower().strip(),
#         phone=phone.strip(),
#         school=school.strip(),
#         class_and_profile=class_and_profile.strip(),
#         city=city.strip(),
#         birthdate=birthdate,

#         supervisor_name=supervisor_name.strip(),
#         supervisor_surname=supervisor_surname.strip(),
#         supervisor_info=supervisor_info.strip(),

#         previous_accomplishments=previous_accomplishments,
#         about = about.strip(),
#         interests = interests.strip(),
#         contributions= contributions.strip(),
#         inspiration = inspiration.strip(),

#         topic=topic.strip(),
#         whytopic=whytopic.strip(),
#         whyinteresting=whyinteresting.strip(),
#         experience=experience.strip(),
#         ways_of_grabing_interest=ways_of_grabing_interest.strip(),

#         video_file_path=video_file_path,
#         rules_accepted=rules_accepted,
#         privacy_policy_accepted=privacy_policy_accepted,
#     )
#     try:
#         db.add(new_contestant)
#         db.commit()
#         db.refresh(new_contestant)
#         background_tasks.add_task(
#             send_confirmation_email,
#             new_contestant.email,
#             new_contestant.name,
#             "prelegenta"
#         )
#     except IntegrityError:
#         db.rollback()
#         raise HTTPException(status_code=400, detail="Ten adres E-mail jest już zarejestrowany")
#     return JSONResponse(
#         status_code=200,
#         content={"success": True, "message": "Pomyślnie zarejestrowano!"}
#     )

# # UNCOMMENT WHEN OPENING

@app.post("/viewerForm")
@limiter.limit("10/minute")
async def handle_viewerform(
    request: Request,
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    surname: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    school: str | None = Form(None),
    class_and_profile: str | None = Form(None),
    is_contestant_close: str = Form(...),
    rules_accepted: bool = Form(...),
    privacy_policy_accepted: bool = Form(...),
    db: Session = Depends(get_db),
):
    new_viewer = Viewer(
        name=name.strip(),
        surname=surname.strip(),
        email=email.lower().strip(),
        phone=phone.strip(),
        school=school,
        class_and_profile=class_and_profile,
        is_contestant_close=is_contestant_close,
        rules_accepted=rules_accepted,
        privacy_policy_accepted=privacy_policy_accepted,
    )
    new_voter = Voter(
        email=email.lower().strip(),
    )
    try:
        db.add(new_viewer)
        db.add(new_voter)
        db.commit()
        db.refresh(new_viewer)
        db.refresh(new_voter)
        background_tasks.add_task(
            send_confirmation_email,
            new_viewer.email,
            new_viewer.name,
            "widza"
        )
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Ten adres E-mail jest już zarejestrowany")
    return JSONResponse(
        status_code=200,
        content={"success": True, "message": "Pomyślnie zarejestrowano!"}
    )

# @app.post("/volunteerForm")
# @limiter.limit("10/minute")
# async def handle_volunteerform(
#     request: Request,
#     background_tasks: BackgroundTasks,
#     name: str = Form(...),
#     surname: str = Form(...),
#     email: str = Form(...),
#     phone: str = Form(...),
#     school: str = Form(...),
#     class_and_profile: str = Form(...),
#     birthdate: date = Form(...),
#     facebook_link: str | None = Form(None),
#     rules_accepted: bool = Form(...),
#     privacy_policy_accepted: bool = Form(...),
#     db: Session = Depends(get_db),
# ):
#     new_volunteer = Volunteer(
#         name=name.strip(),
#         surname=surname.strip(),
#         email=email.lower().strip(),
#         phone=phone.strip(),
#         school=school.strip(),
#         class_and_profile=class_and_profile.strip(),
#         birthdate=birthdate,
#         facebook_link=facebook_link,
#         rules_accepted=rules_accepted,
#         privacy_policy_accepted=privacy_policy_accepted,
#     )
#     try:
#         db.add(new_volunteer)
#         db.commit()
#         db.refresh(new_volunteer)
#         background_tasks.add_task(
#             send_confirmation_email,
#             new_volunteer.email,
#             new_volunteer.name,
#             "wolontariusza"
#         )
#     except IntegrityError as e:
#         db.rollback()
#         return JSONResponse(status_code=400, content={"success": False, "message": "Ten adres E-mail jest już zarejestrowany"})
#     return JSONResponse(
#         status_code=200,
#         content={"success": True, "message": "Pomyślnie zarejestrowano!"}
#      )

@app.post("/groupForm")
@limiter.limit("10/minute")
async def handle_groupform(
    request: Request,
    background_tasks: BackgroundTasks,
    supervisor_name: str = Form(...),
    supervisor_surname: str = Form(...),
    email: str = Form(...),
    school: str = Form(...),
    class_and_profile: str = Form(...),
    number_of_participants: int = Form(...),
    
    rules_accepted: bool = Form(...),
    privacy_policy_accepted: bool = Form(...),
    db: Session = Depends(get_db),
):
    new_group = Group(
        supervisor_name=supervisor_name.strip(),
        supervisor_surname=supervisor_surname.strip(),
        email=email.lower().strip(),
        school=school.strip(),
        class_and_profile=class_and_profile.strip(),
        number_of_participants=number_of_participants,
        number_of_added_emails=0,

        rules_accepted=rules_accepted,
        privacy_policy_accepted=privacy_policy_accepted,
    )
    try:
        db.add(new_group)
        db.commit()
        db.refresh(new_group)
        background_tasks.add_task(
            send_confirmation_email,
            new_group.email,
            new_group.supervisor_name,
            "opiekuna grupy"
        )
    except IntegrityError as e:
        db.rollback()
        return JSONResponse(status_code=400, content={"success": False, "message": "Ten adres E-mail jest już zarejestrowany"})
    return JSONResponse(
        status_code=200,
        content={"success": True, "message": "Pomyślnie zarejestrowano!"}
     )

#ADMIN PAGES
load_dotenv("SECRET_KEY.env")
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is not set")
ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 240


templates=Jinja2Templates(directory="templates")
def get_current_admin(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("admin_session")
    if not token:
        raise HTTPException(status_code=401)
    
    try:
        payload = jwt.decode(token,SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401)
    
    admin = db.query(AdminUser).filter(
        AdminUser.username == username
    ).first()

    if not admin:
        raise HTTPException(status_code=401)

    return admin

@app.exception_handler(HTTPException)
async def auth_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401 and request.url.path.startswith("/admin"):
        return RedirectResponse("/admin/login")
    return JSONResponse(status_code=exc.status_code, content={"detail":exc.detail})


@app.get("/admin/dashboard")
def admin_dashboard(
    request: Request, tab: str = "viewer",
    search: str = "", favourites_only: bool=False, show_hidden: bool=False,
    admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)
):
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    
    if tab in ["contestant", "volunteer", "manager"]:
        if not admin.is_superadmin:
            raise HTTPException(
                status_code=403,
                detail="Superadmin access required."
            )

    TAB_CONFIG = {
        "contestant": Contestant,
        "viewer": Viewer,
        "volunteer": Volunteer, 
        "group": Group,
    }
    model = TAB_CONFIG.get(tab)
    if not model:
        return Response("", status_code=204)
    
    query = db.query(model).order_by(model.id.asc())
    search = search.strip()

    if tab=="contestant":
        if favourites_only:
            query = query.filter(model.favourite == True)
        
    if tab!="group" and not show_hidden:
            query = query.filter(model.hidden == False)
    if search:
        all_items = query.all()
        
        def score(item):
            if tab == "group":
                text = f"{item.supervisor_name} {item.supervisor_surname} {item.school} {item.email}"
            else:
                text = f"{item.name} {item.surname} {item.email}"
            
            return fuzz.token_set_ratio(search.lower(), text.lower())

        scored = [(item,score(item)) for item in all_items]
        scored.sort(key = lambda x:x[1], reverse=True);

        top_3 = [item for item, s in scored[:3]]

        others = [
            item for item, s in scored[3:]
            if s > 70
        ]
        data = top_3+others
        
        query = None

    show_hidden_bool = show_hidden == "on"

    data = data if search else query.all()
    count = len(data)
    context = {
            "request": request,
            "tab": tab,
            "data": data,
            "admin": admin,
            "favourites_only": favourites_only,
            "show_hidden": show_hidden_bool,
            "search": search,
            "count": count
        }
    if is_ajax:
        return templates.TemplateResponse(f"{tab}.html",context)

    return templates.TemplateResponse(
        "admin_dashboard.html",
        context
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

@app.get("/admin/login")
def adminloginpage(request: Request):
    return templates.TemplateResponse(
        "admin_login.html",
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
    
    if not admin or not verify_password(password,admin.password_hash):
        return templates.TemplateResponse(
            "admin_login.html",
            {
                "request": request,
                "error": "Błedna nazwa użytkownika lub hasło."
            }
        )
    
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    token = jwt.encode(
        {"sub": admin.username, "exp": expire},
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    response = RedirectResponse("/admin/dashboard", status_code=303)

    response.set_cookie(
        key="admin_session",
        value=token,
        httponly=True,
        secure=True,
        samesite="strict"
    )

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
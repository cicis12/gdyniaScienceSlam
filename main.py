from fastapi import FastAPI, Form, File, UploadFile, Depends, Request, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles 
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from database import SessionLocal, engine, Base, get_db
import shutil, os
from models import Viewer, Contestant, Volunteer, AdminUser, Voter, Vote, Group, SystemSetting
import uuid
from datetime import date
from video import save_video
from sqlalchemy.exc import IntegrityError
from security import verify_password
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
from urllib.parse import urlparse, parse_qs
from pydantic import BaseModel


#set up needed variables
app = FastAPI()
app.mount("/static",StaticFiles(directory="static"), name="static")
BASE_DIR = Path(__file__).resolve().parent

templates=Jinja2Templates(directory="templates")

#rate limiter
# limiter = Limiter(key_func=get_remote_address, storage_uri="redis://localhost:6379")

# app.state.limiter = limiter

# @app.exception_handler(RateLimitExceeded)
# async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
#     raise HTTPException(status_code=429, detail="Zbyt dużo zapytań. Spróbuj ponownie później")


#serve pages (@app.get)
@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("client/index.html", {"request": request, "header_title": "Gdynia Science Slam", "page_name":"home"})

@app.get("/team")
def team(request: Request):
    return templates.TemplateResponse("client/team.html", {"request": request, "header_title": "Zespół - Gdynia Science Slam", "page_name":"team"})

@app.get("/registration")
def registration(request: Request):
    return templates.TemplateResponse("client/registration.html", {"request": request, "header_title": "Rejestracja - Gdynia Science Slam", "page_name":"registration"})

@app.get("/about")
def about(request: Request):
    return templates.TemplateResponse("client/about.html", {"request": request, "header_title": "O Nas - Gdynia Science Slam", "page_name":"about"})

@app.get("/previous_editions")
def previous(request: Request):
    return templates.TemplateResponse("client/previous.html", {"request": request, "header_title": "Poprzednie edycje - Gdynia Science Slam", "page_name":"previous_editions"})

@app.get("/partners")
def partners(request: Request):
    return templates.TemplateResponse("client/partners.html", {"request": request, "header_title": "Partnerzy - Gdynia Science Slam", "page_name":"partners"})

@app.get("/documents")
def documents(request: Request):
    return templates.TemplateResponse("client/documents.html", {"request": request, "header_title": "Dokumenty - Gdynia Science Slam", "page_name":"documents"})

# @app.get("/groups")
# def groups(request: Request):
#     return templates.TemplateResponse("client/partners.html", {"request": request, "header_title": "Rejestracja - Gdynia Science Slam", "page_name":"groups"})

@app.get("/topics")
def topics(request: Request):
    return templates.TemplateResponse("client/topics.html", {"request": request, "header_title": "Tematy - Gdynia Science Slam", "page_name":"topics"})

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

# @app.post("/viewerForm")
# @limiter.limit("10/minute")
# async def handle_viewerform(
#     request: Request,
#     background_tasks: BackgroundTasks,
#     name: str = Form(...),
#     surname: str = Form(...),
#     email: str = Form(...),
#     phone: str = Form(...),
#     school: str | None = Form(None),
#     class_and_profile: str | None = Form(None),
#     is_contestant_close: str = Form(...),
#     rules_accepted: bool = Form(...),
#     privacy_policy_accepted: bool = Form(...),
#     db: Session = Depends(get_db),
# ):
#     new_viewer = Viewer(
#         name=name.strip(),
#         surname=surname.strip(),
#         email=email.lower().strip(),
#         phone=phone.strip(),
#         school=school,
#         class_and_profile=class_and_profile,
#         is_contestant_close=is_contestant_close,
#         rules_accepted=rules_accepted,
#         privacy_policy_accepted=privacy_policy_accepted,
#     )
#     new_voter = Voter(
#         email=email.lower().strip(),
#     )
#     try:
#         db.add(new_viewer)
#         db.add(new_voter)
#         db.commit()
#         db.refresh(new_viewer)
#         db.refresh(new_voter)
#         background_tasks.add_task(
#             send_confirmation_email,
#             new_viewer.email,
#             new_viewer.name,
#             "widza"
#         )
#     except IntegrityError as e:
#         db.rollback()
#         raise HTTPException(status_code=400, detail="Ten adres E-mail jest już zarejestrowany")
#     return JSONResponse(
#         status_code=200,
#         content={"success": True, "message": "Pomyślnie zarejestrowano!"}
#     )

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

# @app.post("/groupForm")
# @limiter.limit("10/minute")
# async def handle_groupform(
#     request: Request,
#     background_tasks: BackgroundTasks,
#     supervisor_name: str = Form(...),
#     supervisor_surname: str = Form(...),
#     email: str = Form(...),
#     school: str = Form(...),
#     class_and_profile: str = Form(...),
#     number_of_participants: int = Form(...),
    
#     rules_accepted: bool = Form(...),
#     privacy_policy_accepted: bool = Form(...),
#     db: Session = Depends(get_db),
# ):
#     new_group = Group(
#         supervisor_name=supervisor_name.strip(),
#         supervisor_surname=supervisor_surname.strip(),
#         email=email.lower().strip(),
#         school=school.strip(),
#         class_and_profile=class_and_profile.strip(),
#         number_of_participants=number_of_participants,
#         number_of_added_emails=0,

#         rules_accepted=rules_accepted,
#         privacy_policy_accepted=privacy_policy_accepted,
#     )
#     try:
#         db.add(new_group)
#         db.commit()
#         db.refresh(new_group)
#         background_tasks.add_task(
#             send_confirmation_email,
#             new_group.email,
#             new_group.supervisor_name,
#             "opiekuna grupy"
#         )
#     except IntegrityError as e:
#         db.rollback()
#         return JSONResponse(status_code=400, content={"success": False, "message": "Ten adres E-mail jest już zarejestrowany"})
#     return JSONResponse(
#         status_code=200,
#         content={"success": True, "message": "Pomyślnie zarejestrowano!"}
#      )

#ADMIN PAGES
# load_dotenv("SECRET_KEY.env")
# SECRET_KEY = os.getenv("SECRET_KEY")
# if not SECRET_KEY:
#     raise RuntimeError("SECRET_KEY is not set")
# ALGORITHM = "HS256"

# ACCESS_TOKEN_EXPIRE_MINUTES = 240



# def get_current_admin(request: Request, db: Session = Depends(get_db)):
#     token = request.cookies.get("admin_session")
#     if not token:
#         raise HTTPException(status_code=401)
    
#     try:
#         payload = jwt.decode(token,SECRET_KEY, algorithms=[ALGORITHM])
#         username = payload.get("sub")
#     except JWTError:
#         raise HTTPException(status_code=401)
    
#     admin = db.query(AdminUser).filter(
#         AdminUser.username == username
#     ).first()

#     if not admin:
#         raise HTTPException(status_code=401)

#     return admin

# @app.exception_handler(HTTPException)
# async def auth_exception_handler(request: Request, exc: HTTPException):
#     if exc.status_code == 401 and request.url.path.startswith("/admin"):
#         return RedirectResponse("/admin/login")
#     return JSONResponse(status_code=exc.status_code, content={"detail":exc.detail})

# EMAIL SENDER
# def get_emails_from_table(
#     table: str,
#     db: Session
#     ):
#     TABLE_MAP = {
#         "contestants": Contestant,
#         "viewers": Viewer,
#         "volunteers": Volunteer,
#         "groups": Group,
#     }

#     model=TABLE_MAP.get(table)

#     if not model:
#         return []

#     results = db.query(model.email).all()

#     return [r[0] for r in results if r[0]]

# @app.get("/admin/emailsender")
# def admin_email_sender(
#     request: Request,
#     admin: AdminUser = Depends(get_current_admin),
# ):
#     if not admin.is_superadmin:
#         raise HTTPException(
#             status_code=403,
#             detail="Superadmin access required."
#         )
#     return templates.TemplateResponse("sendMails.html", {"request": request})

# @app.post("/admin/send-email")
# async def sendemailform(
#     table: str = Form(...),
#     subject: str = Form(...),
#     body: str = Form(...),
#     mode: str = Form(...),
#     test_email: str = Form(None),
#     db: Session = Depends(get_db),
# ):

#     if mode == "test":
#         recipients = [test_email]

#     else:
#         # get emails from DB table
#         recipients = get_emails_from_table(table,db)

#     for email in recipients:
#         send_email(
#             to_email=email,
#             content=body,
#             subject=subject,
#         )

#     return RedirectResponse(
#         url="/admin/emailsender?success=1",
#         status_code=303
#     )

# @app.post("/admin/send-email/preview")
# async def preview_email(
#     table: str = Form(...),
#     subject: str = Form(...),
#     body: str = Form(...),
#     mode: str = Form(...),
#     test_email: str = Form(None),
# ):
#     return templates.TemplateResponse(
#         "email_confirm.html",
#         {
#             "request": {},
#             "table": table,
#             "subject": subject,
#             "body": body,
#             "mode": mode,
#             "test_email": test_email,
#         }
#     )

# @app.get("/admin/dashboard")
# def admin_dashboard(
#     request: Request, tab: str = "viewer",
#     search: str = "", favourites_only: bool=False, show_hidden: bool=False,
#     admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)
# ):
#     is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    
#     if tab in ["contestant", "volunteer", "manager"]:
#         if not admin.is_superadmin:
#             raise HTTPException(
#                 status_code=403,
#                 detail="Superadmin access required."
#             )

#     TAB_CONFIG = {
#         "contestant": Contestant,
#         "viewer": Viewer,
#         "volunteer": Volunteer, 
#         "group": Group,
#     }
#     model = TAB_CONFIG.get(tab)
#     if not model:
#         return Response("", status_code=204)
    
#     query = db.query(model).order_by(model.id.asc())
#     search = search.strip()

#     if tab=="contestant":
#         if favourites_only:
#             query = query.filter(model.favourite == True)
        
#     if tab!="group" and not show_hidden:
#             query = query.filter(model.hidden == False)
#     if search:
#         all_items = query.all()
        
#         def score(item):
#             if tab == "group":
#                 text = f"{item.supervisor_name} {item.supervisor_surname} {item.school} {item.email}"
#             else:
#                 text = f"{item.name} {item.surname} {item.email}"
            
#             return fuzz.token_set_ratio(search.lower(), text.lower())

#         scored = [(item,score(item)) for item in all_items]
#         scored.sort(key = lambda x:x[1], reverse=True);

#         top_3 = [item for item, s in scored[:3]]

#         others = [
#             item for item, s in scored[3:]
#             if s > 70
#         ]
#         data = top_3+others
        
#         query = None

#     show_hidden_bool = show_hidden == "on"

#     data = data if search else query.all()
#     count = len(data)
#     context = {
#             "request": request,
#             "tab": tab,
#             "data": data,
#             "admin": admin,
#             "favourites_only": favourites_only,
#             "show_hidden": show_hidden_bool,
#             "search": search,
#             "count": count
#         }
#     if is_ajax:
#         return templates.TemplateResponse(f"{tab}.html",context)

#     return templates.TemplateResponse(
#         "admin_dashboard.html",
#         context
#     )

# @app.post("/admin/toggle-favourite/{item_id}")
# def toggle_favourite(
#     item_id: int,
#     tab: str = "contestant",
#     db: Session = Depends(get_db),
#     admin: AdminUser = Depends(get_current_admin),
# ):
#     model = {
#         "contestant": Contestant,
#         "viewer": Viewer,
#         "volunteer": Volunteer
#     }.get(tab)

#     if not model:
#         return RedirectResponse("/admin/dashboard", status_code=303)
    
#     item = db.query(model).get(item_id)
#     item.favourite = not item.favourite
#     db.commit()
#     return RedirectResponse(f"/admin/dashboard?tab={tab}", status_code=303)

# @app.post("/admin/toggle-hidden/{item_id}")
# def toggle_hidden(
#     request: Request,
#     item_id: int,
#     redirect_url: str = Form(...),
#     db: Session = Depends(get_db),
#     admin: AdminUser = Depends(get_current_admin),
# ):

#     parsed = urlparse(redirect_url)
#     tab = parse_qs(parsed.query).get("tab", ["viewer"])[0]

#     model = {
#         "contestant": Contestant,
#         "viewer": Viewer,
#         "volunteer": Volunteer,
#         "group": Group,
#     }.get(tab)

#     if not model:
#         return RedirectResponse("/admin/dashboard", status_code=303)
    
#     item = db.get(model,item_id)
#     item.hidden = not item.hidden
#     db.commit()

#     if request.headers.get("X-Requested-With") == "XMLHttpRequest":
#         return Response(status_code=200)

#     return RedirectResponse(redirect_url, status_code=303)

# @app.post("/admin/group/{group_id}/add-email")
# def add_email(
#     group_id: int,
#     background_tasks: BackgroundTasks,
#     email: str = Form(...),
#     db: Session = Depends(get_db),
#     admin: AdminUser = Depends(get_current_admin),
# ):
#     group = db.get(Group, group_id)
#     if not group:
#         return JSONResponse(status_code=404, content={"ok": False, "error": "Nie znaleziono grupy."})

#     group.number_of_added_emails += 1
#     new_voter = Voter(
#         email = email.lower().strip(),
#     )
#     try:
#         db.add(new_voter)
#         db.commit()
#         db.refresh(new_voter)
#         background_tasks.add_task(
#             send_confirmation_email,
#             new_voter.email,
#             "",
#             "widza"
#         )
#     except IntegrityError as e:
#         db.rollback()
#         return JSONResponse(status_code=400, content={"ok": False, "error": "Ten adres E-mail jest już zarejestrowany"})

#     return {"ok": True, "new_count": group.number_of_added_emails}

# @app.get("/admin/login")
# def adminloginpage(request: Request):
#     return templates.TemplateResponse(
#         "admin_login.html",
#         {"request": request}
#     )


# @app.post("/adminLogin", response_class=HTMLResponse)
# @limiter.limit("5/minute")
# async def admin_login(
#     request: Request,
#     username: str = Form(...),
#     password: str = Form(...),

#     db: Session = Depends(get_db)
# ):
#     admin = db.query(AdminUser).filter(
#         AdminUser.username == username
#     ).first()
    
#     if not admin or not verify_password(password,admin.password_hash):
#         return templates.TemplateResponse(
#             "admin_login.html",
#             {
#                 "request": request,
#                 "error": "Błedna nazwa użytkownika lub hasło."
#             }
#         )
    
#     expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

#     token = jwt.encode(
#         {"sub": admin.username, "exp": expire},
#         SECRET_KEY,
#         algorithm=ALGORITHM
#     )

#     response = RedirectResponse("/admin/dashboard", status_code=303)

#     response.set_cookie(
#         key="admin_session",
#         value=token,
#         httponly=True,
#         secure=True,
#         samesite="strict"
#     )

#     return response

# CONTESTANT_VID_DIR = BASE_DIR / "uploads" / "filmikuczestnik"

# @app.get("/admin/video/{filename}")
# def get_video(filename: str, admin: AdminUser = Depends(get_current_admin)):
#     file_path = (CONTESTANT_VID_DIR / filename).resolve()

#     if not file_path.exists():
#         raise HTTPException(status_code=404, detail="File not found")

#     if CONTESTANT_VID_DIR not in file_path.parents:
#         raise HTTPException(status_code=403,detail="Invalid path")

#     return FileResponse(file_path)


# VOTING
# from vote import create_voter_token, get_current_voter, decode_voter
# @app.post("/vote/login")
# def vote_login(
#     email: str = Form(...),
#     db: Session = Depends(get_db)
# ):
#     voter = db.query(Voter).filter(Voter.email == email.lower().strip()).first()

#     if not voter:
#         return Response("Email not registered", status_code=404)

#     token = create_voter_token(voter.id, voter.email)

#     response = RedirectResponse("/vote", status_code=303)

#     response.set_cookie(
#         key="voter_session",
#         value=token,
#         httponly=True,
#         secure=True,
#         samesite="lax"
#     )

#     return response

# @app.get("/vote")
# def vote_page(
#     request: Request,
#     db: Session = Depends(get_db)
# ):
#     voting_enabled = get_setting(db, "voting_enabled", "true") == "true"

    
#     voter = decode_voter(request,db)

#     if not voting_enabled:
#         return templates.TemplateResponse("vote_closed.html",{"request": request, "voter": voter})

#     votes_left = 0
#     voted_choices = set()
#     if voter:
#         used = db.query(Vote).filter(Vote.voter_id == voter.id).count()
#         votes_left = 3 - used
#         voted_choices = {
#         v.choice
#         for v in db.query(Vote).filter(Vote.voter_id == voter.id).all()
#     }

#     CONTESTANTS=[
#         {"id": 1, "name": "Laura Grafińska", "topic": "Dlaczego mężczyzna pomylił żonę z kapeluszem?", "img": "/static/assets/images/contestants/47 Laura.webp"},
#         {"id": 2, "name": "Wojciech Kubik", "topic": "Dlaczego jedne dźwięki brzmią dobrze, a inne nie?", "img": "/static/assets/images/contestants/48 Wojciech.webp"},
#         {"id": 3, "name": "Gabriela Żuprańska", "topic": "Harmonia mózgu", "img": "/static/assets/images/contestants/49 Gabriela.webp"},
#         {"id": 4, "name": "Krzysztof Florek", "topic": "Badania próbek konsumenckich a geopolityka", "img": "/static/assets/images/contestants/50 Krzysztof.webp"},
#         {"id": 5, "name": "Natalia Monkiewicz", "topic": "Dlaczego twój układ immunologiczny się nie buntuje - i co by się stało gdyby to zrobił?", "img": "/static/assets/images/contestants/51 Natalia.webp"},
#         {"id": 6, "name": "Hanna Grzybek", "topic": "Co łączy śmierć ze śmiechu i szalone krowy?", "img": "/static/assets/images/contestants/52 Hanna.webp"},
#         {"id": 7, "name": "Stanisław Matuszewski", "topic": "Prąd elektryczny jako ruch cząsteczek elementarnych - czyli wykorzystywanie zjawisk kwantowych w elektrotechnice", "img": "/static/assets/images/contestants/53 Stanisław.webp"},
#         {"id": 8, "name": "Dorota Słowi", "topic": "Psychoza AI - czy chatbot może być Twoim przyjacielem?", "img": "/static/assets/images/contestants/54 Dorota .webp"},
#         {"id": 9, "name": "Małgorzata Narożnik", "topic": "InfecSense - platforma niewczesnych opatrunków aktywnych", "img": "/static/assets/images/contestants/55 Małgorzata.webp"},
#         {"id": 10, "name": "Malina Graczyk", "topic": "Dobranoc czyli dzień dobry - Selekcja pamięci podczas snu", "img": "/static/assets/images/contestants/56 Malina.webp"},
#         {"id": 11, "name": "Lilia Hrynkiewicz", "topic": "Jak księżyc zaprowadzi nas na Marsa?", "img": "/static/assets/images/contestants/57 Lilia.webp"},
#     ]

    

#     return templates.TemplateResponse("vote.html", {
#         "request": request,
#         "voter": voter,
#         "votes_left": votes_left,
#         "contestants": CONTESTANTS,
#         "voted_choices": list(voted_choices)
#     })


# class VoteRequest(BaseModel):
#     votes: list[int]


# @app.post("/vote/submit")
# def submit_votes(
#     data: VoteRequest,
#     voter: Voter = Depends(get_current_voter),
#     db: Session = Depends(get_db)
# ):

#     if get_setting(db, "voting_enabled", "true") != "true":
#         raise HTTPException(403, "Voting is closed")

#     existing_votes = db.query(Vote).filter(Vote.voter_id == voter.id).all()

#     existing_choices = {v.choice for v in existing_votes}

#     # 1. prevent duplicates in same request
#     if len(data.votes) != len(set(data.votes)):
#         raise HTTPException(400, "Duplicate votes in request")

#     # 2. prevent voting twice for same contestant
#     duplicates = set(data.votes) & existing_choices
#     if duplicates:
#         raise HTTPException(
#             400,
#             f"Already voted for: {list(duplicates)}"
#         )

#     # 3. enforce max limit
#     remaining = 3 - len(existing_votes)
#     if len(data.votes) > remaining:
#         raise HTTPException(400, "Vote limit exceeded")

#     # 4. insert votes
#     for choice in data.votes:
#         db.add(Vote(
#             voter_id=voter.id,
#             choice=choice
#         ))

#     db.commit()

#     remaining = 3 - db.query(Vote).filter(Vote.voter_id == voter.id).count()
#     return {
#         "ok": True,
#         "votes_left": remaining
#     }

# @app.post("/admin/toggle-voting")
# def toggle_voting(
#     request: Request,
#     redirect_url: str = Form("/admin/dashboard?tab=voting"),
#     db: Session = Depends(get_db),
#     admin: AdminUser = Depends(get_current_admin),
# ):
#     setting = db.get(SystemSetting, "voting_enabled")

#     if not setting:
#         setting = SystemSetting(key="voting_enabled", value="true")
#         db.add(setting)
#     else:
#         setting.value = "false" if setting.value == "true" else "true"

#     db.commit()

#     # AJAX support (same pattern as toggle_hidden)
#     if request.headers.get("X-Requested-With") == "XMLHttpRequest":
#         return Response(status_code=200)

#     return RedirectResponse(redirect_url, status_code=303)

# def get_setting(db: Session, key: str, default="false"):
#     s = db.get(SystemSetting, key)
#     return s.value if s else default




# def require_superadmin(admin: AdminUser = Depends(get_current_admin)):
#     if not admin.is_superadmin:
#         raise HTTPException(status_code=403, detail="Superadmin only")
#     return admin

# @app.get("/admin/manage_votes")
# def manage_votes(
#     request: Request,
#     db: Session = Depends(get_db),
#     admin: AdminUser = Depends(require_superadmin),
# ):
#     voting_enabled = get_setting(db, "voting_enabled", "false") == "true"

#     total_votes = db.query(Vote).count()

#     raw_results = (
#         db.query(Vote.choice, func.count(Vote.id))
#         .group_by(Vote.choice)
#         .all()
#     )

#     results_map = {choice: count for choice, count in raw_results}

#     contestants = [
#         {"id": 1, "name": "Laura Grafińska"},
#         {"id": 2, "name": "Wojciech Kubik"},
#         {"id": 3, "name": "Gabriela Żuprańska"},
#         {"id": 4, "name": "Krzysztof Florek"},
#         {"id": 5, "name": "Natalia Monkiewicz"},
#         {"id": 6, "name": "Hanna Grzybek"},
#         {"id": 7, "name": "Stanisław Matuszewski"},
#         {"id": 8, "name": "Dorota Słowi"},
#         {"id": 9, "name": "Małgorzata Narożnik"},
#         {"id": 10, "name": "Malina Graczyk"},
#         {"id": 11, "name": "Lilia Hrynkiewicz"},
#     ]

#     for c in contestants:
#         c["votes"] = results_map.get(c["id"], 0)

#     return templates.TemplateResponse("admin_manage_votes.html", {
#         "request": request,
#         "admin": admin,
#         "voting_enabled": voting_enabled,
#         "contestants": contestants,
#         "total_votes": total_votes
#     })


# @app.get("/admin/voters/bulk-preview")
# def preview_bulk_voters(
#     db: Session = Depends(get_db),
#     admin: AdminUser = Depends(require_superadmin),
# ):
#     viewers = (
#         db.query(Viewer)
#         .all()
#     )

#     emails = {v.email.lower().strip() for v in viewers}

#     existing = {
#         email for (email,) in db.query(Voter.email).all()
#     }

#     to_create = emails - existing

#     return {
#         "eligible_viewers": len(emails),
#         "already_voters": len(emails - to_create),
#         "new_voters": len(to_create),
#     }



# @app.post("/admin/voters/bulk-create")
# def bulk_create_voters(
#     request: Request,
#     db: Session = Depends(get_db),
#     admin: AdminUser = Depends(require_superadmin),
# ):
#     viewers = (
#         db.query(Viewer)
#         .all()
#     )

#     emails = {v.email.lower().strip() for v in viewers}

#     existing = {
#         email for (email,) in db.query(Voter.email).all()
#     }

#     new_emails = emails - existing

#     if not new_emails:
#         return {"ok": True, "created": 0}

#     new_voters = [
#         Voter(email=email)
#         for email in new_emails
#     ]

#     db.add_all(new_voters)
#     db.commit()

#     # AJAX support like your existing system
#     if request.headers.get("X-Requested-With") == "XMLHttpRequest":
#         return {"ok": True, "created": len(new_voters)}

#     return RedirectResponse("/admin/manage_votes", status_code=303)


# @app.post("/admin/voters/filter-by-hidden-viewers")
# def filter_voters_by_hidden_viewers(
#     db: Session = Depends(get_db),
#     admin: AdminUser = Depends(require_superadmin),
# ):
#     viewers = db.query(Viewer).all()

#     viewer_map = {
#         v.email.lower().strip(): v.hidden
#         for v in viewers
#     }

#     voters = db.query(Voter).all()

#     to_delete = []

#     for voter in voters:
#         email = voter.email.lower().strip()

#         # no matching viewer OR viewer not hidden → delete
#         if email not in viewer_map or viewer_map[email] != True:
#             to_delete.append(voter)

#     deleted_count = len(to_delete)

#     for v in to_delete:
#         db.delete(v)

#     db.commit()

#     return {
#         "ok": True,
#         "deleted": deleted_count,
#         "remaining": db.query(Voter).count()
#     }


# @app.get("/admin/voters/filter-preview")
# def filter_preview(
#     db: Session = Depends(get_db),
#     admin: AdminUser = Depends(require_superadmin),
# ):
#     viewers = db.query(Viewer).all()

#     viewer_map = {
#         v.email.lower().strip(): v.hidden
#         for v in viewers
#     }

#     voters = db.query(Voter).all()

#     to_delete = 0
#     keep = 0

#     for voter in voters:
#         email = voter.email.lower().strip()

#         if email not in viewer_map or viewer_map[email] != True:
#             to_delete += 1
#         else:
#             keep += 1

#     return {
#         "total_voters": len(voters),
#         "to_delete": to_delete,
#         "keep": keep
#     }

# @app.post("/admin/votes/delete-all")
# def delete_all_votes(
#     request: Request,
#     db: Session = Depends(get_db),
#     admin: AdminUser = Depends(require_superadmin),
# ):
#     deleted = db.query(Vote).delete()  # bulk delete, fast

#     db.commit()

#     # AJAX support (consistent with your system)
#     if request.headers.get("X-Requested-With") == "XMLHttpRequest":
#         return {"ok": True, "deleted": deleted}

#     return RedirectResponse("/admin/manage_votes", status_code=303)
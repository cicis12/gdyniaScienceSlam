from fastapi import FastAPI, Form, File, UploadFile, Depends, Request, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles 
from pathlib import Path
from sqlalchemy.orm import Session
from database import SessionLocal, engine, Base, get_db
import shutil, os
from models import Viewer, Contestant, Volunteer, AdminUser
import uuid
from datetime import date
from video import save_video
from sqlalchemy.exc import IntegrityError
from security import verify_password
from datetime import datetime, timedelta
from dotenv import load_dotenv
from jose import jwt
#set up needed variables


app = FastAPI()
app.mount("/static",StaticFiles(directory="static"), name="static")
BASE_DIR = Path(__file__).resolve().parent

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

@app.get("/admin/login", response_class=FileResponse)
def adminloginpage():
    return BASE_DIR/"admin_login.html"
# Handle Post (@app.post)
@app.post("/contestantForm")
async def handle_contestantform(
    name: str = Form(...),
    surname: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    school: str = Form(...),
    class_and_profile: str = Form(...),
    city: str = Form(...),
    birthdate: date = Form(...),

    supervisor_name: str = Form(...),
    supervisor_surname: str = Form(...),
    supervisor_info: str = Form(...),

    previous_accomplishments: str | None = Form(None),
    about: str = Form(...),
    interests: str = Form(...),
    contributions: str = Form(...),
    story: str = Form(...),

    topic: str = Form(...),
    whytopic: str = Form(...),
    persuation: str = Form(...),
    experience: str = Form(...),
    ways_of_grabing_interest: str = Form(...),

    video: UploadFile | None = File(None),
    rules_accepted: bool = Form(...),

    db: Session = Depends(get_db),
):
    video_file_path = None
    if video and video.filename:
        if video.size > 0:
            video_file_path = await save_video(video)
    
    new_contestant = Contestant(
        name=name.strip(),
        surname=surname.strip(),
        email=email.lower().strip(),
        phone=phone.strip(),
        school=school.strip(),
        class_and_profile=class_and_profile.strip(),
        city=city.strip(),
        birthdate=birthdate,

        supervisor_name=supervisor_name.strip(),
        supervisor_surname=supervisor_surname.strip(),
        supervisor_info=supervisor_info.strip(),

        previous_accomplishments=previous_accomplishments,
        about = about.strip(),
        interests = interests.strip(),
        contributions= contributions.strip(),
        story = story.strip(),

        topic=topic.strip(),
        whytopic=whytopic.strip(),
        persuation=persuation.strip(),
        experience=experience.strip(),
        ways_of_grabing_interest=ways_of_grabing_interest.strip(),

        video_file_path=video_file_path,
        rules_accepted=rules_accepted,
    )
    try:
        db.add(new_contestant)
        db.commit()
        db.refresh(new_contestant)
    except IntegrityError:
        db.rollback()
        return JSONResponse(status_code=400, content={"success": False, "message": "Ten adres E-mail jest już zarejestrowany"})
    return JSONResponse(
        status_code=200,
        content={"success": True, "message": "Pomyślnie zarejestrowano!"}
    )

@app.post("/viewerForm")
async def handle_viewerform(
    name: str = Form(...),
    surname: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    school: str | None = Form(None),
    class_and_profile: str | None = Form(None),
    rules_accepted: bool = Form(...),

    db: Session = Depends(get_db),
):
    new_viewer = Viewer(
        name=name.strip(),
        surname=surname.strip(),
        email=email.lower().strip(),
        phone=phone.strip(),
        school=school,
        class_and_profile=class_and_profile,
        rules_accepted=rules_accepted,
    )
    try:
        db.add(new_viewer)
        db.commit()
        db.refresh(new_viewer)
    except IntegrityError:
        db.rollback()
        return JSONResponse(status_code=400, content={"success": False, "message": "Ten adres E-mail jest już zarejestrowany"})
    return JSONResponse(
        status_code=200,
        content={"success": True, "message": "Pomyślnie zarejestrowano!"}
    )

@app.post("/volunteerForm")
async def handle_volunteerform(
    name: str = Form(...),
    surname: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    school: str = Form(...),
    class_and_profile: str = Form(...),
    birthdate: date = Form(...),
    rules_accepted: bool = Form(...),

    db: Session = Depends(get_db),
):
    new_volunteer = Volunteer(
        name=name.strip(),
        surname=surname.strip(),
        email=email.lower().strip(),
        phone=phone.strip(),
        school=school.strip(),
        class_and_profile=class_and_profile.strip(),
        birthdate=birthdate,
        rules_accepted=rules_accepted,
    )
    try:
        db.add(new_volunteer)
        db.commit()
        db.refresh(new_volunteer)
    except IntegrityError:
        db.rollback()
        return JSONResponse(status_code=400, content={"success": False, "message": "Ten adres E-mail jest już zarejestrowany"})
    return JSONResponse(
        status_code=200,
        content={"success": True, "message": "Pomyślnie zarejestrowano!"}
    )


#ADMIN PAGES
load_dotenv("SECRET_KEY.env")
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
def get_current_admin(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("admin_session")
    if not token:
        raise HTTPException(status_code=401)
    
    try:
        payload = jwt.decode(token,SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
    except:
        raise HTTPException(status_code=401)
    
    admin = db.query(AdminUser).filter(
        AdminUser.username == username
    ).first()

    if not admin:
        raise HTTPException(status_code=401)

    return admin

@app.exception_handler(HTTPException)
async def auth_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401:
        return RedirectResponse("/admin/login")
    return JSONResponse(status_code=exc.status_code, content={"detail":exc.detail})


@app.get("/admin/dashboard", response_class=FileResponse)
def admin_dashboard(admin : AdminUser = Depends(get_current_admin)):
    return BASE_DIR/"admin_dashboard.html"

@app.post("/adminLogin")
async def admin_login(
    username: str = Form(...),
    password: str = Form(...),

    db: Session = Depends(get_db)
):
    admin = db.query(AdminUser).filter(
        AdminUser.username == username
    ).first()
    
    if not admin or not verify_password(password,admin.password_hash):
        return JSONResponse(status_code=400, content={"success": False, "message": "Błędna nazwa użytkownika lub hasło"})
    
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

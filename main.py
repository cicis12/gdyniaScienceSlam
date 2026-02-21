from fastapi import FastAPI, Form, File, UploadFile, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles 
from pathlib import Path
from sqlalchemy.orm import Session
from database import SessionLocal, engine, Base, get_db
import shutil, os
from models import Viewer, Contestant
import uuid
from datetime import date
from video import save_video
from sqlalchemy.exc import IntegrityError


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

@app.get("/exampleform", response_class=FileResponse)
def form():
    return BASE_DIR/"contestantform.html"

@app.get("/ping")
def ping():
    return {"message": "pong"}

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
        raise HTTPException(status_code=400, detail="Email already registered")

@app.post("/testForm")
async def handle_exampleform(
    name: str = Form(...),
    surname: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    school: str=Form(None),
    parentconsent: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    existing_viewer= db.query(Viewer).filter(Viewer.email == email).first()
    if existing_viewer:
        return {
            "status": "exists",
            "message": "viewer with this email already exists",
            "viewer_id": existing_viewer.id

            # later add frontend support for the display of this message, and an option to change the submit data
        }
    file_path= f"uploads/zgodawidz/{uuid.uuid4()}_{parentconsent.filename}"
    with open(file_path,"wb") as buffer:
        shutil(parentconsent.file,buffer)
    
    viewer = Viewer(
        name=name,
        surname=surname,
        school=school,
        email=email,
        phone=phone,
        consent_file_path=file_path
    )
    db.add(viewer)
    db.commit()
    db.refresh(viewer)
    return {"message": "Form submitted successfully!", "id": viewer.id}
from fastapi import FastAPI, Form, File, UploadFile, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles 
from pathlib import Path
from sqlalchemy.orm import Session
from database import SessionLocal, engine, Base, get_db
import shutil, os
from models import Viewer
import uuid


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
    return BASE_DIR/"form.html"

@app.get("/ping")
def ping():
    return {"message": "pong"}

# Handle Post (@app.post)

@app.post("/testForm")
def handle_exampleform(
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
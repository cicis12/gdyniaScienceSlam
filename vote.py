from fastapi import FastAPI, Form, File, UploadFile, Depends, Request, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles 
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from database import SessionLocal, engine, Base, get_db
import shutil, os
from models import Viewer, Contestant, Volunteer, AdminUser, Voter, Vote, Group
import uuid
from datetime import date
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta
from dotenv import load_dotenv
from jose import jwt
from jose import JWTError

load_dotenv("VOTER_SECRET_KEY.env")
VOTER_KEY = os.getenv("VOTER_SECRET_KEY")
if not VOTER_KEY:
    raise RuntimeError("VOTER_SECRET_KEY is not set")
ALGORITHM = "HS256"


def create_voter_token(voter_id: int, email: str):
    payload = {
        "sub": str(voter_id),
        "exp": datetime.utcnow() + timedelta(hours=12)
    }
    return jwt.encode(payload,VOTER_KEY,algorithm=ALGORITHM)

def get_current_voter(request: Request, db: Session = Depends(get_db)):
    token=request.cookies.get("voter_session")

    if not token:
        raise HTTPException(401)

    try:
        payload = jwt.decode(token, VOTER_KEY, algorithms=[ALGORITHM])
        voter_id = int(payload.get("sub"))
    except JWTError:
        raise HTTPException(401)

    voter = db.query(Voter).get(voter_id)

    if not voter:
        raise HTTPException(401)
    
    return voter

def decode_voter(request: Request, db: Session = Depends(get_db)):
    token=request.cookies.get("voter_session")

    if not token:
        return None

    try:
        payload = jwt.decode(token, VOTER_KEY, algorithms=[ALGORITHM])
        voter_id = int(payload.get("sub"))
        return db.query(Voter).get(voter_id)
    except:
        return None
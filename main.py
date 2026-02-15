from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles 
from pathlib import Path

app = FastAPI()

app.mount("/static",StaticFiles(directory="static"), name="static")
BASE_DIR = Path(__file__).resolve().parent

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
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from models import FormInfo, FormVersion, FormSubmission
from forms import FormDefinition, FormPayload, build_submission_model

router = APIRouter()
# Create Jinja2Templates locally to avoid circular imports with main.py
templates = Jinja2Templates(directory="templates")


@router.post("/api/forms/submit")
def submit_form(payload: FormPayload, db: Session = Depends(get_db)):
    form = db.query(FormInfo).filter(FormInfo.id == payload.form_id).first()
    if not form or not form.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Formularz niedostępny.")
    
    version = db.query(FormVersion).filter(
        FormVersion.id == payload.form_version_id,
        FormVersion.form_id == form.id
    ).first()

    if not version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Niezgodna wersja formularza.")

    parsed_definition = FormDefinition.model_validate(version.definition)
    DynamicValidator = build_submission_model(parsed_definition)

    try:
        validated_answers = DynamicValidator.model_validate(payload.answers).model_dump()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    submission = FormSubmission(
        form_id=form.id,
        form_version_id=version.id,
        data=validated_answers
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)

    return {"status": "success", "submission_id": submission.id}


@router.get("/forms/{slug}", response_class=HTMLResponse)
def render_form_page(slug: str, request: Request, db: Session = Depends(get_db)):
    form = db.query(FormInfo).filter(FormInfo.slug == slug).first()

    if not form or not form.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Formularz niedostępny.")
    
    version = db.query(FormVersion).filter(
        FormVersion.id == form.cur_version_id, 
        FormVersion.form_id == form.id
    ).first()

    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nie znaleziono aktywnej wersji formularza.")

    return templates.TemplateResponse(
        "form.html",
        {
            "request": request,
            "form": form,
            "version": version
        }
    )
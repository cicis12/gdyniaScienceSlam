from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.datastructures import UploadFile
from starlette.concurrency import run_in_threadpool
import json
from form_uploads import save_uploads, remove_uploads
from pydantic import ValidationError
from bs4 import BeautifulSoup
import logging

from templating import create_templates
from sqlalchemy.orm import Session

from database import get_db
from models import FormInfo, FormVersion, FormSubmission
from forms import FormDefinition, FormPayload, build_submission_model

logger = logging.getLogger(__name__)
router = APIRouter()
# Create Jinja2Templates locally to avoid circular imports with main.py
templates = create_templates()


@router.post("/api/forms/submit")
async def submit_form(request: Request, db: Session = Depends(get_db)):
    uploads = {}
    parsed = None
    try:
        content_type = request.headers.get('content-type', '').lower()
        if content_type.startswith('multipart/form-data'):
            parsed = await request.form(max_files=3, max_fields=1, max_part_size=256 * 1024)
            payload = FormPayload.model_validate_json(parsed.get('payload', ''))
            for key, value in parsed.multi_items():
                if key == 'payload' and not isinstance(value, UploadFile):
                    continue
                if not key.startswith('file:') or not isinstance(value, UploadFile) or key[5:] in uploads:
                    raise HTTPException(422, 'Nieprawidłowy załącznik formularza.')
                uploads[key[5:]] = value
        elif content_type.startswith('application/json'):
            payload = FormPayload.model_validate(await request.json())
        else:
            raise HTTPException(415, 'Nieobsługiwany format formularza.')
        return await run_in_threadpool(save_submission, payload, uploads, db)
    except (ValidationError, ValueError, TypeError, json.JSONDecodeError):
        return JSONResponse(status_code=422, content={'detail': 'Sprawdź poprawność danych formularza.'})
    finally:
        if parsed is not None:
            await parsed.close()


def save_submission(payload, uploads, db):
    form = db.query(FormInfo).filter(FormInfo.id == payload.form_id).with_for_update().first()
    if not form or not form.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Formularz niedostępny.")
    
    version = db.query(FormVersion).filter(
        FormVersion.id == payload.form_version_id,
        FormVersion.form_id == form.id
    ).first()

    if not version or version.id != form.cur_version_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Niezgodna wersja formularza.")

    try:
        parsed_definition = FormDefinition.model_validate(version.definition)
        DynamicValidator = build_submission_model(parsed_definition)
    except (ValidationError, TypeError, ValueError):
        logger.error('Invalid form definition: form=%s version=%s', form.id, version.id)
        raise HTTPException(500, 'Formularz jest chwilowo niedostępny. Spróbuj ponownie później.') from None

    file_fields = {field.name for field in parsed_definition.fields if field.type.value == 'file'}
    if set(uploads) - file_fields:
        raise HTTPException(422, 'Ten formularz nie przyjmuje wskazanego załącznika.')
    answers = dict(payload.answers)
    for name in file_fields:
        if name in uploads:
            answers[name] = uploads[name].filename
        elif answers.get(name) not in (None, ''):
            return JSONResponse(status_code=422, content={
                'code': 'invalid_answers', 'message': 'Wybierz plik do przesłania.', 'fields': [name],
            })
    try:
        validated_answers = DynamicValidator.model_validate(answers).model_dump()
    except ValidationError as error:
        labels = {}
        types = {}
        for field in parsed_definition.fields:
            labels[field.name] = BeautifulSoup(field.question, 'html.parser').get_text(' ', strip=True)
            types[field.name] = field.type.value
            if field.name2:
                labels[field.name2] = BeautifulSoup(field.question2 or field.question, 'html.parser').get_text(' ', strip=True)
                types[field.name2] = field.type.value
        messages, invalid_fields = [], []
        for item in error.errors(include_input=False, include_url=False):
            name = str(item['loc'][0])
            invalid_fields.append(name)
            label = labels.get(name, 'Pole')[:120]
            if item['type'] == 'string_too_long':
                instruction = 'skróć odpowiedź do 10 000 znaków.'
            elif types.get(name) == 'file':
                instruction = 'dołącz wymagany plik.'
            elif types.get(name) == 'email':
                instruction = 'wpisz poprawny adres e-mail.'
            elif types.get(name) == 'list_choice':
                instruction = 'wybierz jedną z dostępnych opcji.'
            elif types.get(name) == 'checkbox':
                instruction = 'zaznacz wymagane pole.'
            else:
                instruction = 'uzupełnij to pole poprawną wartością.'
            messages.append(f'{label}: {instruction}')
        return JSONResponse(status_code=422, content={
            'code': 'invalid_answers', 'message': ' '.join(messages[:3]), 'fields': invalid_fields,
        })

    try:
        accepted_types = {field.name: field.accepted_types for field in parsed_definition.fields if field.type.value == 'file'}
        attachments = save_uploads(uploads, accepted_types) if uploads else {}
    except HTTPException as error:
        if error.status_code != 422:
            raise
        return JSONResponse(status_code=422, content={
            'code': 'invalid_answers', 'message': error.detail, 'fields': list(uploads),
        })
    validated_answers.update(attachments)
    submission = FormSubmission(
        form_id=form.id,
        form_version_id=version.id,
        data=validated_answers
    )
    db.add(submission)
    try:
        db.flush()
        submission_id = submission.id
        db.commit()
    except Exception:
        db.rollback()
        remove_uploads(attachments)
        logger.error('Form submission could not be saved: form=%s version=%s', form.id, version.id)
        raise HTTPException(500, 'Nie udało się zapisać formularza. Spróbuj ponownie za chwilę.') from None

    return {"status": "success", "submission_id": submission_id}


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
        request, "form.html",
        {
            "request": request,
            "form": form,
            "version": version
        }
    )
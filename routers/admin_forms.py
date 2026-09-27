from datetime import datetime
from typing import List, Optional, Any, Dict, Literal
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr, create_model
from sqlalchemy.orm import Session

from database import get_db, Base
from models import FormInfo, FormVersion, SystemSetting
from forms import FormField, FormDefinition, FieldType
from fastapi.responses import FileResponse, HTMLResponse

router = APIRouter(prefix="/admin/forms", tags=["Admin Forms"])
templates = Jinja2Templates(directory="templates")

class CreateFormPayload(BaseModel):
    slug: str
    name: str
    display_name: str
    description: Optional[str] = None
    enabled: bool = True
    fields: List[FormField]

class CreateVersionPayload(BaseModel):
    display_name: str
    description: Optional[str] = None
    fields: List[FormField]

# main site for form management
@router.get("", response_class=HTMLResponse)
def admin_forms_dashboard(request: Request, db: Session = Depends(get_db)):
    forms = db.query(FormInfo).all()
    setting = db.get(SystemSetting, "registration_form_ids")
    selected_registration_form_ids = []
    if setting and setting.value:
        try:
            selected_registration_form_ids = [int(value) for value in setting.value.split(",") if value]
        except ValueError:
            selected_registration_form_ids = []
    return templates.TemplateResponse("admin/form_builder.html", {
        "request": request,
        "forms": forms,
        "selected_registration_form_ids": selected_registration_form_ids,
    })


@router.post("/registration-selection")
def save_registration_form_selection(
    form_ids: List[int] = Form(default=[]),
    db: Session = Depends(get_db),
):
    selected_ids = list(dict.fromkeys(form_ids))
    if len(selected_ids) > 3:
        raise HTTPException(status_code=400, detail="Możesz wybrać maksymalnie 3 formularze.")

    if selected_ids:
        enabled_ids = {
            form.id for form in db.query(FormInfo)
            .filter(FormInfo.id.in_(selected_ids), FormInfo.enabled.is_(True))
            .all()
        }
        if enabled_ids != set(selected_ids):
            raise HTTPException(status_code=400, detail="Można wybrać tylko aktywne formularze.")

    setting = db.get(SystemSetting, "registration_form_ids")
    value = ",".join(str(form_id) for form_id in selected_ids)
    if setting:
        setting.value = value
    else:
        db.add(SystemSetting(key="registration_form_ids", value=value))
    db.commit()
    return RedirectResponse("/admin/forms", status_code=303)

# active form version change
@router.post("/{form_id}/set-active/{version_id}")
def set_active_version(form_id: int, version_id: int, db: Session = Depends(get_db)):
    form = db.query(FormInfo).filter(FormInfo.id == form_id).first()
    version = db.query(FormVersion).filter(FormVersion.id == version_id, FormVersion.form_id == form_id).first()
    
    if not form or not version:
        raise HTTPException(status_code=404, detail="Formularz lub wersja nie istnieje.")
        
    form.cur_version_id = version.id
    db.commit()
    return {"status": "ok", "active_version_id": version.id}

@router.get("/{form_id}/version/{version_id}")
def get_form_version(form_id: int, version_id: int, db: Session = Depends(get_db)):
    form = db.query(FormInfo).filter(FormInfo.id == form_id).first()
    version = db.query(FormVersion).filter(
        FormVersion.id == version_id,
        FormVersion.form_id == form_id
    ).first()

    if not form or not version:
        raise HTTPException(status_code=404, detail="Formularz lub wersja nie istnieje.")

    return {
        "form_id": form.id,
        "name": form.name,
        "slug": form.slug,
        "display_name": version.display_name,
        "description": version.description,
        "fields": version.definition.get("fields", [])
    }

# create a new form
@router.post("/create")
def create_form(payload: CreateFormPayload, db: Session = Depends(get_db)):
    if db.query(FormInfo).filter((FormInfo.slug == payload.slug) | (FormInfo.name == payload.name)).first():
        raise HTTPException(status_code=400, detail="Slug lub nazwa formularza już istnieje.")

    new_form = FormInfo(
        slug=payload.slug,
        name=payload.name,
        enabled=payload.enabled,
        cur_version_id=0
    )
    db.add(new_form)
    db.flush()

    first_ver = FormVersion(
        form_id=new_form.id,
        version_num=1,
        display_name=payload.display_name,
        description=payload.description,
        definition={"fields": [f.model_dump() for f in payload.fields]}
    )
    db.add(first_ver)
    db.flush()

    new_form.cur_version_id = first_ver.id
    db.commit()
    return {"status": "ok", "form_id": new_form.id, "version_id": first_ver.id}

# add a new version to a form
@router.post("/{form_id}/new-version")
def create_new_version(form_id: int, payload: CreateVersionPayload, db: Session = Depends(get_db)):
    form = db.query(FormInfo).filter(FormInfo.id == form_id).first()
    if not form:
        raise HTTPException(status_code=404, detail="Formularz nie istnieje.")

    latest_ver = db.query(FormVersion).filter(FormVersion.form_id == form.id).order_by(FormVersion.version_num.desc()).first()
    next_num = (latest_ver.version_num + 1) if latest_ver else 1

    new_ver = FormVersion(
        form_id=form.id,
        version_num=next_num,
        display_name=payload.display_name,
        description=payload.description,
        definition={"fields": [f.model_dump() for f in payload.fields]}
    )
    db.add(new_ver)
    db.flush()

    db.commit()
    return {"status": "ok", "version_id": new_ver.id, "version_num": next_num}

# preview a draft
@router.post("/preview-draft", response_class=HTMLResponse)
def preview_draft(request: Request, payload: FormDefinition):
    return templates.TemplateResponse("admin/_rendered_preview.html", {
        "request": request,
        "fields": payload.fields
    })

# preview a saved version
@router.get("/preview-version/{version_id}", response_class=HTMLResponse)
def preview_saved_version(version_id: int, request: Request, db: Session = Depends(get_db)):
    version = db.query(FormVersion).filter(FormVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Wersja nie znaleziona.")
    
    definition = FormDefinition.model_validate(version.definition)
    return templates.TemplateResponse("admin/_rendered_preview.html", {
        "request": request,
        "fields": definition.fields,
        "display_name": version.display_name,
        "description": version.description
    })
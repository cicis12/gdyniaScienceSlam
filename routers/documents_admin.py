from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from database import get_db
import document_content
from document_content import Document, MAX_DOCUMENTS, MAX_PDF_BYTES, get_documents, save_documents, validate_pdf
from templating import create_templates

templates = create_templates()


def build_router(require_superadmin):
    router = APIRouter(prefix='/admin/documents', dependencies=[Depends(require_superadmin)])

    def render(request, db, admin, error=None, status_code=200):
        return templates.TemplateResponse('admin/documents.html', {
            'request': request, 'admin': admin, 'documents': get_documents(db), 'error': error,
        }, status_code=status_code)

    def find(documents, document_id):
        document = next((item for item in documents if item.id == document_id), None)
        if document is None:
            raise HTTPException(404)
        return document

    @router.get('')
    def dashboard(request: Request, db: Session = Depends(get_db), admin=Depends(require_superadmin)):
        return render(request, db, admin)

    async def store(request, db, admin, document_id, title, year, enabled, sort_order, pdf):
        documents = get_documents(db)
        original = find(documents, document_id) if document_id else None
        new_path = None
        try:
            if not original and len(documents) >= MAX_DOCUMENTS:
                raise ValueError('Możesz dodać maksymalnie 100 dokumentów.')
            filename = original.filename if original else 'dokument.pdf'
            if pdf and pdf.filename:
                filename = Path(pdf.filename.replace('\\', '/')).name
            document = Document(id=original.id if original else uuid4().hex, title=title, year=year,
                                enabled=enabled, sort_order=sort_order, filename=filename,
                                file=original.file if original else 'uploads/documents/' + uuid4().hex + '.pdf')
            if pdf and pdf.filename:
                data = await run_in_threadpool(validate_pdf, await pdf.read(MAX_PDF_BYTES + 1))
                document_content.DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
                new_path = document_content.DOCUMENTS_DIR / (uuid4().hex + '.pdf')
                new_path.write_bytes(data)
                document.file = 'uploads/documents/' + new_path.name
            elif not original:
                raise ValueError('Dodaj plik PDF.')
            if original:
                documents.remove(original)
            documents.append(document)
            save_documents(db, documents)
            db.commit()
        except Exception as error:
            db.rollback()
            if new_path:
                new_path.unlink(missing_ok=True)
            if isinstance(error, ValueError):
                return render(request, db, admin, str(error), 422)
            raise
        return RedirectResponse('/admin/documents?saved=1', 303)

    @router.post('')
    async def add(request: Request, title: str = Form(...), year: int = Form(2026, ge=2000, le=2100),
                  enabled: bool = Form(False), sort_order: int = Form(0, ge=0, le=100000),
                  pdf: UploadFile = File(...), db: Session = Depends(get_db), admin=Depends(require_superadmin)):
        return await store(request, db, admin, None, title, year, enabled, sort_order, pdf)

    @router.post('/{document_id}')
    async def edit(document_id: str, request: Request, title: str = Form(...), year: int = Form(2026, ge=2000, le=2100),
                   enabled: bool = Form(False), sort_order: int = Form(0, ge=0, le=100000),
                   pdf: UploadFile | None = File(None), db: Session = Depends(get_db), admin=Depends(require_superadmin)):
        return await store(request, db, admin, document_id, title, year, enabled, sort_order, pdf)

    @router.post('/{document_id}/delete')
    def delete(document_id: str, db: Session = Depends(get_db)):
        documents = get_documents(db)
        documents.remove(find(documents, document_id))
        save_documents(db, documents)
        db.commit()
        return RedirectResponse('/admin/documents?saved=1', 303)

    return router

"""HTTP endpoints for document uploads, status, listing, and deletion."""

from uuid import UUID
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from app.db.session import get_db
from app.db.session import get_engine
from app.api.dependencies import current_user
from app.models.user import User
from app.models.document import Document
from app.schemas.document import DocumentResponse, DocumentListResponse, DocumentUploadResponse, DocumentStatusResponse
from app.services.document_service import owned_kb, owned_document, process_upload
from app.services.storage import delete_file
from app.core.config import get_settings
router = APIRouter(prefix='/knowledge-bases/{kb_id}/documents', tags=['Documents'])

def _process_upload_in_worker(user_id, kb_id, filename: str, data: bytes):
    """Give the worker its own SQLAlchemy session for the full sync workflow."""
    with sessionmaker(bind=get_engine())() as worker_db:
        return process_upload(worker_db, user_id, kb_id, filename, data)

@router.post('', response_model=DocumentUploadResponse, status_code=201)
async def upload(kb_id: UUID, file: UploadFile=File(...), user: User=Depends(current_user)):
    max_bytes = get_settings().MAX_UPLOAD_MB * 1_000_000
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(413, 'File too large')
    # Keep the full synchronous DB, extraction, and embedding workflow on one
    # worker thread with its own session; request dependency sessions stay on
    # the server thread that authenticated the user.
    doc = await run_in_threadpool(_process_upload_in_worker, user.id, kb_id, file.filename or '', data)
    return DocumentUploadResponse(document=DocumentResponse.model_validate(doc), message='Document processed' if doc.status == 'ready' else 'Processing failed; see processing_error')

@router.get('', response_model=DocumentListResponse)
def listing(kb_id: UUID, user: User=Depends(current_user), db: Session=Depends(get_db)):
    owned_kb(db, user.id, kb_id)
    items = list(db.scalars(select(Document).where(Document.knowledge_base_id == kb_id).order_by(Document.created_at.desc())).all())
    return DocumentListResponse(items=items, total=len(items))

@router.get('/{doc_id}/status', response_model=DocumentStatusResponse)
def status(kb_id: UUID, doc_id: UUID, user: User=Depends(current_user), db: Session=Depends(get_db)):
    d = owned_document(db, user.id, kb_id, doc_id)
    return DocumentStatusResponse(document_id=d.id, status=d.status, page_count=d.page_count, chunk_count=d.chunk_count, processing_error=d.processing_error, processed_at=d.processed_at)

@router.delete('/{doc_id}', status_code=204)
def delete(kb_id: UUID, doc_id: UUID, user: User=Depends(current_user), db: Session=Depends(get_db)):
    d = owned_document(db, user.id, kb_id, doc_id)
    if d.cloudinary_public_id:
        try:
            delete_file(d.cloudinary_public_id, d.cloudinary_resource_type or 'raw')
        except Exception as exc:
            raise HTTPException(502, 'Could not delete the original file from Cloudinary; document metadata was kept') from exc
    db.delete(d)
    db.commit()

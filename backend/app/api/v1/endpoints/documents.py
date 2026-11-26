"""HTTP endpoints for document uploads, status, listing, and deletion."""

from uuid import UUID
from datetime import datetime, timedelta, timezone
import os
from threading import Lock
from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker
from app.db.session import get_db
from app.db.session import get_engine
from app.api.dependencies import current_user, subscribed_user
from app.models.user import User
from app.models.document import Document
from app.models.conversation import Conversation
from app.schemas.document import DocumentResponse, DocumentListResponse, DocumentUploadResponse, DocumentStatusResponse
from app.services.document_service import owned_kb, owned_document, process_upload
from app.services.file_validation import validate_upload
from app.services.storage import delete_file
from app.core.config import max_upload_mb
router = APIRouter(prefix='/knowledge-bases/{kb_id}/documents', tags=['Documents'])

class DocumentUpdate(BaseModel):
    original_filename: str | None = Field(default=None, min_length=1, max_length=255)
    is_archived: bool | None = None
    is_pinned: bool | None = None
_upload_processing_lock = Lock()

def _fail_stale_processing(db: Session, kb_id: UUID):
    """Mark uploads abandoned by a worker restart so they don't stay pending forever."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=15)
    result = db.execute(
        update(Document)
        .where(
            Document.knowledge_base_id == kb_id,
            Document.status.in_(['pending', 'processing']),
            Document.updated_at < cutoff,
        )
        .values(
            status='failed',
            processing_error='Processing stopped before it completed. Delete this entry and upload the file again.',
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount:
        db.commit()
    else:
        db.rollback()

def _process_upload_in_worker(user_id, kb_id, document_id, filename: str, data: bytes):
    """Serialize heavy indexing and give it a dedicated database session."""
    with _upload_processing_lock:
        with sessionmaker(bind=get_engine())() as worker_db:
            return process_upload(worker_db, user_id, kb_id, filename, data, document_id=document_id)

@router.post('', response_model=DocumentUploadResponse, status_code=201)
async def upload(kb_id: UUID, background_tasks: BackgroundTasks, file: UploadFile=File(...), user: User=Depends(subscribed_user), db: Session=Depends(get_db)):
    max_bytes = max_upload_mb() * 1_000_000
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(413, 'File too large')
    owned_kb(db, user.id, kb_id)
    name, mime = validate_upload(file.filename or '', data, max_upload_mb())
    doc = Document(
        knowledge_base_id=kb_id,
        original_filename=name,
        content_type=mime,
        file_size_bytes=len(data),
        status='pending',
        chunk_count=0,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    # Serverless instances can be frozen or recycled after the HTTP response,
    # so Vercel must complete indexing within the request instead of relying
    # on an in-process background task. Keep the task-based path for persistent
    # hosts such as Render, where the process stays alive after the response.
    if os.getenv('VERCEL'):
        processed_doc = await run_in_threadpool(
            _process_upload_in_worker, user.id, kb_id, doc.id, name, data
        )
        if processed_doc is None:
            raise HTTPException(500, 'Document processing could not be started')
        message = (
            'Document processed'
            if processed_doc.status == 'ready'
            else processed_doc.processing_error or 'Document processing failed'
        )
        return DocumentUploadResponse(
            document=DocumentResponse.model_validate(processed_doc),
            message=message,
        )

    # Persistent hosts return once accepted and continue indexing in-process.
    # The worker opens its own DB session; the request session is never shared.
    background_tasks.add_task(_process_upload_in_worker, user.id, kb_id, doc.id, name, data)
    return DocumentUploadResponse(document=DocumentResponse.model_validate(doc), message='Upload accepted; processing in background.')

@router.get('', response_model=DocumentListResponse)
def listing(kb_id: UUID, user: User=Depends(current_user), db: Session=Depends(get_db)):
    owned_kb(db, user.id, kb_id)
    _fail_stale_processing(db, kb_id)
    items = list(db.scalars(select(Document).where(Document.knowledge_base_id == kb_id).order_by(Document.is_pinned.desc(), Document.created_at.desc())).all())
    return DocumentListResponse(items=items, total=len(items))

@router.get('/{doc_id}/status', response_model=DocumentStatusResponse)
def status(kb_id: UUID, doc_id: UUID, user: User=Depends(current_user), db: Session=Depends(get_db)):
    d = owned_document(db, user.id, kb_id, doc_id)
    _fail_stale_processing(db, kb_id)
    db.refresh(d)
    return DocumentStatusResponse(document_id=d.id, status=d.status, page_count=d.page_count, chunk_count=d.chunk_count, processing_error=d.processing_error, processed_at=d.processed_at)

@router.delete('/{doc_id}', status_code=204)
def delete(kb_id: UUID, doc_id: UUID, user: User=Depends(current_user), db: Session=Depends(get_db)):
    d = owned_document(db, user.id, kb_id, doc_id)
    if d.cloudinary_public_id:
        try:
            delete_file(d.cloudinary_public_id, d.cloudinary_resource_type or 'raw')
        except Exception as exc:
            raise HTTPException(502, 'Could not delete the original file from Cloudinary; document metadata was kept') from exc
    db.query(Conversation).filter(Conversation.document_id == doc_id).delete(synchronize_session=False)
    db.delete(d)
    db.commit()

@router.patch('/{doc_id}', response_model=DocumentResponse)
def update_document(kb_id: UUID, doc_id: UUID, data: DocumentUpdate, user: User=Depends(current_user), db: Session=Depends(get_db)):
    document = owned_document(db, user.id, kb_id, doc_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(document, key, value)
    db.commit()
    db.refresh(document)
    return document

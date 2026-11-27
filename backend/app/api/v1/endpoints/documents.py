"""HTTP endpoints for document uploads, status, listing, and deletion."""

from uuid import UUID
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.dependencies import current_user, subscribed_user
from app.models.user import User
from app.models.document import Document
from app.models.conversation import Conversation
from app.schemas.document import DocumentResponse, DocumentListResponse, DocumentUploadResponse, DocumentStatusResponse
from app.services.document_service import owned_kb, owned_document
from app.services.file_validation import validate_upload
from app.services.storage import delete_file, store_file
from app.services.job_queue import enqueue_index_document
from app.core.config import max_upload_mb
router = APIRouter(prefix='/knowledge-bases/{kb_id}/documents', tags=['Documents'])

class DocumentUpdate(BaseModel):
    original_filename: str | None = Field(default=None, min_length=1, max_length=255)
    is_archived: bool | None = None
    is_pinned: bool | None = None
@router.post('', response_model=DocumentUploadResponse, status_code=202)
async def upload(kb_id: UUID, file: UploadFile=File(...), user: User=Depends(subscribed_user), db: Session=Depends(get_db)):
    max_bytes = max_upload_mb() * 1_000_000
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(413, f'File is too large. Maximum size is {max_upload_mb()}MB.')
    owned_kb(db, user.id, kb_id)
    name, mime = validate_upload(file.filename or '', data, max_upload_mb())
    try:
        stored = await run_in_threadpool(store_file, name, data)
    except Exception as exc:
        raise HTTPException(502, 'The original file could not be saved. Please check your connection and try again.') from exc
    doc = Document(
        knowledge_base_id=kb_id,
        original_filename=name,
        content_type=mime,
        file_size_bytes=len(data),
        cloudinary_public_id=stored['public_id'],
        cloudinary_resource_type=stored['resource_type'],
        storage_url=stored['url'],
        status='pending',
        progress_stage='uploading',
        chunk_count=0,
    )
    try:
        db.add(doc)
        db.flush()
        enqueue_index_document(db, doc.id)
        db.commit()
    except Exception as exc:
        db.rollback()
        try:
            await run_in_threadpool(delete_file, stored['public_id'], stored['resource_type'])
        except Exception:
            pass
        raise HTTPException(500, 'The file was uploaded but could not be queued. Please try again.') from exc
    db.refresh(doc)
    return DocumentUploadResponse(document=DocumentResponse.model_validate(doc), message='Upload accepted. Your file is being processed.')

@router.get('/upload-config')
def upload_config(kb_id: UUID, user: User=Depends(current_user), db: Session=Depends(get_db)):
    owned_kb(db, user.id, kb_id)
    return {'max_upload_mb': max_upload_mb(), 'allowed_extensions': ['.pdf', '.txt', '.docx', '.jpg', '.jpeg', '.png', '.heic']}

@router.get('', response_model=DocumentListResponse)
def listing(kb_id: UUID, user: User=Depends(current_user), db: Session=Depends(get_db)):
    owned_kb(db, user.id, kb_id)
    items = list(db.scalars(select(Document).where(Document.knowledge_base_id == kb_id).order_by(Document.is_pinned.desc(), Document.created_at.desc())).all())
    return DocumentListResponse(items=items, total=len(items))

@router.get('/{doc_id}/status', response_model=DocumentStatusResponse)
def status(kb_id: UUID, doc_id: UUID, user: User=Depends(current_user), db: Session=Depends(get_db)):
    d = owned_document(db, user.id, kb_id, doc_id)
    db.refresh(d)
    return DocumentStatusResponse(document_id=d.id, status=d.status, progress_stage=d.progress_stage, page_count=d.page_count, chunk_count=d.chunk_count, processing_error=d.processing_error, processed_at=d.processed_at, ocr_used=d.ocr_used, ocr_confidence=d.ocr_confidence, low_ocr_confidence=d.ocr_used and (d.ocr_confidence is None or d.ocr_confidence < 60))

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

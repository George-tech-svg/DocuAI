"""Validate, extract, index, and manage uploaded documents."""

from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.knowledge_base import KnowledgeBase
from app.services.knowledge_base_service import get_knowledge_base, KnowledgeBaseNotFoundError
from app.services.file_validation import validate_upload
from app.services.extraction import extract_pages
from app.services.chunking import chunk_pages
from app.services.embeddings import embed_texts
from app.services.storage import store_file
from app.core.config import get_settings

def owned_kb(db, user_id, kb_id):
    """Ensure the requested knowledge base belongs to the current user."""
    try:
        return get_knowledge_base(db, user_id, kb_id)
    except KnowledgeBaseNotFoundError:
        raise HTTPException(404, 'Knowledge base not found')

def owned_document(db, user_id, kb_id, doc_id):
    """Ensure the document belongs to a knowledge base owned by the user."""
    owned_kb(db, user_id, kb_id)
    d = db.scalar(select(Document).where(Document.id == doc_id, Document.knowledge_base_id == kb_id))
    if not d:
        raise HTTPException(404, 'Document not found')
    return d

def process_upload(db: Session, user_id, kb_id, filename: str, data: bytes):
    """Store document metadata, extract text, generate embeddings, and update status."""
    owned_kb(db, user_id, kb_id)
    name, mime = validate_upload(filename, data, get_settings().MAX_UPLOAD_MB)
    doc = Document(knowledge_base_id=kb_id, original_filename=name, content_type=mime, file_size_bytes=len(data), status='pending', chunk_count=0)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    try:
        pages = extract_pages(name, data)
        chunks = chunk_pages(pages)
        if not chunks:
            raise ValueError('No extractable text found. Scanned PDFs require OCR.')
        vectors = embed_texts([content for _, content in chunks])
        for i, ((page, content), embedding) in enumerate(zip(chunks, vectors)):
            db.add(DocumentChunk(document_id=doc.id, chunk_index=i, page_number=page, content=content, embedding=embedding))
        stored = store_file(name, data)
        if stored:
            doc.cloudinary_public_id = stored['public_id']
            doc.cloudinary_resource_type = stored['resource_type']
            doc.storage_url = stored['url']
        doc.page_count = len(pages)
        doc.chunk_count = len(chunks)
        doc.status = 'ready'
        doc.processed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(doc)
    except Exception as exc:
        db.rollback()
        doc = db.get(Document, doc.id)
        doc.status = 'failed'
        doc.processing_error = 'Processing failed. Check the server logs for details.'
        db.commit()
        db.refresh(doc)
    return doc

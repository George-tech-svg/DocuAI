"""Validate, extract, index, and manage uploaded documents."""

from datetime import datetime, timezone
import logging
from time import perf_counter
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
from app.services.storage import store_file, delete_file
from app.core.config import get_settings

logger = logging.getLogger(__name__)

def owned_kb(db, user_id, kb_id):
    """Ensure the requested knowledge base belongs to the current user."""
    stored = None
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
    overall_started = perf_counter()
    doc.status = 'processing'
    db.commit()
    logger.info('Document %s processing started (%s bytes).', doc.id, len(data))
    # Uploads may fail during extraction or embedding, before Cloudinary has
    # returned anything. Keep this initialized so the failure handler itself
    # cannot raise UnboundLocalError and strand the document as pending.
    stored = None
    try:
        stage_started = perf_counter()
        logger.info('Document %s: extracting text.', doc.id)
        pages = extract_pages(name, data)
        logger.info('Document %s: extracted %s page(s) in %.1f seconds.', doc.id, len(pages), perf_counter() - stage_started)
        stage_started = perf_counter()
        chunks = chunk_pages(pages)
        if not chunks:
            raise ValueError('No extractable text found. Scanned PDFs require OCR.')
        logger.info('Document %s: created %s text chunk(s).', doc.id, len(chunks))
        stage_started = perf_counter()
        logger.info('Document %s: generating embeddings.', doc.id)
        vectors = embed_texts([content for _, content in chunks])
        logger.info('Document %s: generated embeddings in %.1f seconds.', doc.id, perf_counter() - stage_started)
        for i, ((page, content), embedding) in enumerate(zip(chunks, vectors)):
            db.add(DocumentChunk(document_id=doc.id, chunk_index=i, page_number=page, content=content, embedding=embedding))
        stage_started = perf_counter()
        logger.info('Document %s: saving original file to Cloudinary.', doc.id)
        stored = store_file(name, data)
        logger.info('Document %s: Cloudinary save finished in %.1f seconds.', doc.id, perf_counter() - stage_started)
        doc.cloudinary_public_id = stored['public_id']
        doc.cloudinary_resource_type = stored['resource_type']
        doc.storage_url = stored['url']
        doc.page_count = len(pages)
        doc.chunk_count = len(chunks)
        doc.status = 'ready'
        doc.processed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(doc)
        logger.info('Document %s ready after %.1f seconds.', doc.id, perf_counter() - overall_started)
    except Exception as exc:
        logger.exception('Document processing failed for document %s', doc.id)
        db.rollback()
        if stored:
            try:
                delete_file(stored['public_id'], stored['resource_type'])
            except Exception:
                pass
        doc = db.get(Document, doc.id)
        doc.status = 'failed'
        doc.processing_error = str(exc)[:500] or 'Document processing failed.'
        db.commit()
        db.refresh(doc)
    return doc

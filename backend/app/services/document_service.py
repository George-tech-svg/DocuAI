"""Validate, extract, index, and manage uploaded documents."""

from datetime import datetime, timezone
import logging
from time import perf_counter
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.knowledge_base import KnowledgeBase
from app.services.knowledge_base_service import get_knowledge_base, KnowledgeBaseNotFoundError
from app.services.file_validation import validate_upload
from app.services.extraction import extract_pages
from app.services.chunking import chunk_pages
from app.services.embeddings import iter_embedding_batches
from app.services.storage import store_file, delete_file
from app.core.config import max_extracted_chars, max_upload_mb

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

def process_upload(db: Session, user_id, kb_id, filename: str, data: bytes, document_id=None):
    """Store document metadata, extract text, generate embeddings, and update status."""
    owned_kb(db, user_id, kb_id)
    name, mime = validate_upload(filename, data, max_upload_mb())
    if document_id is None:
        doc = Document(knowledge_base_id=kb_id, original_filename=name, content_type=mime, file_size_bytes=len(data), status='pending', chunk_count=0)
        db.add(doc)
        db.commit()
        db.refresh(doc)
    else:
        doc = db.get(Document, document_id)
        # The user may have deleted the pending record before the worker began.
        if doc is None or doc.knowledge_base_id != kb_id:
            return None
    overall_started = perf_counter()
    processing_document_id = doc.id
    # Uploads may fail during extraction or embedding, before Cloudinary has
    # returned anything. Keep this initialized so the failure handler itself
    # cannot raise UnboundLocalError and strand the document as pending.
    stored = None
    try:
        doc.status = 'processing'
        db.commit()
        logger.info('Document %s processing started (%s bytes).', processing_document_id, len(data))
        stage_started = perf_counter()
        logger.info('Document %s: extracting text.', processing_document_id)
        pages = extract_pages(name, data)
        logger.info('Document %s: extracted %s page(s) in %.1f seconds.', processing_document_id, len(pages), perf_counter() - stage_started)
        extracted_chars = sum(len(text) for _, text in pages)
        if extracted_chars > max_extracted_chars():
            raise ValueError(
                'The extracted document text is too large to index on this service '
                f'(maximum {max_extracted_chars():,} characters).'
            )
        stage_started = perf_counter()
        chunks = chunk_pages(pages)
        if not chunks:
            raise ValueError('No extractable text found. Scanned PDFs require OCR.')
        logger.info('Document %s: created %s text chunk(s).', processing_document_id, len(chunks))
        stage_started = perf_counter()
        logger.info('Document %s: generating embeddings in batches.', processing_document_id)
        for batch_start in range(0, len(chunks), 32):
            batch_chunks = chunks[batch_start:batch_start + 32]
            batch_contents = [content for _, content in batch_chunks]
            vectors = [
                vector
                for vector_batch in iter_embedding_batches(batch_contents, batch_size=16)
                for vector in vector_batch
            ]
            for offset, ((page, content), embedding) in enumerate(zip(batch_chunks, vectors)):
                db.add(DocumentChunk(
                    document_id=processing_document_id,
                    chunk_index=batch_start + offset,
                    page_number=page,
                    content=content,
                    embedding=embedding,
                ))
            # Persist bounded batches and refresh the processing timestamp. If
            # Render terminates the worker, the status endpoint can identify
            # the last point at which real progress was made.
            doc.updated_at = datetime.now(timezone.utc)
            db.commit()
        logger.info('Document %s: generated embeddings in %.1f seconds.', processing_document_id, perf_counter() - stage_started)
        stage_started = perf_counter()
        logger.info('Document %s: saving original file to Cloudinary.', processing_document_id)
        stored = store_file(name, data)
        logger.info('Document %s: Cloudinary save finished in %.1f seconds.', processing_document_id, perf_counter() - stage_started)
        doc.cloudinary_public_id = stored['public_id']
        doc.cloudinary_resource_type = stored['resource_type']
        doc.storage_url = stored['url']
        doc.page_count = len(pages)
        doc.chunk_count = len(chunks)
        doc.status = 'ready'
        doc.processed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(doc)
        logger.info('Document %s ready after %.1f seconds.', processing_document_id, perf_counter() - overall_started)
    except Exception as exc:
        # A user may delete a document while extraction or embedding is in
        # progress. Roll back first and retain the ID separately: touching an
        # expired ORM object after a failed flush can raise PendingRollbackError.
        db.rollback()
        logger.exception('Document processing failed for document %s', processing_document_id)
        if stored:
            try:
                delete_file(stored['public_id'], stored['resource_type'])
            except Exception:
                pass
        db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == processing_document_id))
        result = db.execute(
            Document.__table__.update()
            .where(Document.id == processing_document_id)
            .values(
                status='failed',
                processing_error=str(exc)[:500] or 'Document processing failed.',
                updated_at=datetime.now(timezone.utc),
            )
        )
        if result.rowcount == 0:
            # The row was deleted while this worker was processing it. The
            # chunk cleanup is harmless and the database may have cascaded it.
            db.rollback()
            return None
        db.commit()
        doc = db.get(Document, processing_document_id)
    return doc

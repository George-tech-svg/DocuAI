"""Download and index a single official document without crawling its publisher."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import ipaddress
import logging
import mimetypes
import re
import socket
from urllib.parse import urlparse
import httpx
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from app.core.config import max_extracted_chars
from app.models.entities import LibraryCollection, LibraryDocument, LibraryChunk
from app.services.job_queue import enqueue_library_update
from app.services.chunking import chunk_pages
from app.services.embeddings import iter_embedding_batches
from app.services.ocr import extract_document

logger = logging.getLogger(__name__)
LIBRARY_MAX_BYTES = 50_000_000
_SECTION = re.compile(r'\b(?:section|sec\.?|article|art\.?|regulation|reg\.?)\s+\d+[A-Za-z]?(?:\s*\([^)]{1,50}\))?', re.I)

def validate_official_source_url(url: str) -> str:
    """Accept a direct public HTTPS file URL; never crawl or follow redirects."""
    parsed = urlparse(url.strip())
    host = (parsed.hostname or '').rstrip('.').lower()
    if parsed.scheme != 'https' or not host or parsed.username or parsed.password:
        raise ValueError('Source URL must be a direct HTTPS URL from the official publisher.')
    if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
        raise ValueError('Local or private network source URLs are not allowed.')
    try:
        address = ipaddress.ip_address(host)
        if not address.is_global:
            raise ValueError('Private network source URLs are not allowed.')
    except ValueError as exc:
        if 'not allowed' in str(exc):
            raise
        try:
            resolved = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        except OSError as dns_error:
            raise ValueError('The official source hostname could not be reached.') from dns_error
        if any(not ipaddress.ip_address(item[4][0]).is_global for item in resolved):
            raise ValueError('Source host resolves to a private network address.')
    return url.strip()

def download_official_file(url: str) -> tuple[str, bytes]:
    url = validate_official_source_url(url)
    parts = []
    total = 0
    try:
        with httpx.stream('GET', url, timeout=httpx.Timeout(45, connect=10), follow_redirects=False,
                          headers={'User-Agent': 'DocuMind-Kenya-Library/1.0 (direct official-document download)'}) as response:
            response.raise_for_status()
            length = response.headers.get('content-length')
            if length and int(length) > LIBRARY_MAX_BYTES:
                raise ValueError('Official document exceeds the 50 MB library ingestion limit.')
            for block in response.iter_bytes():
                total += len(block)
                if total > LIBRARY_MAX_BYTES:
                    raise ValueError('Official document exceeds the 50 MB library ingestion limit.')
                parts.append(block)
            content_type = response.headers.get('content-type', '').split(';', 1)[0].lower()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f'The official source returned HTTP {exc.response.status_code}. Check the URL and publisher access terms.') from exc
    except httpx.HTTPError as exc:
        raise RuntimeError('The official document could not be downloaded. Check its URL and try again.') from exc
    data = b''.join(parts)
    path = urlparse(url).path.lower()
    suffix = next((extension for extension in ('.pdf', '.docx', '.txt') if path.endswith(extension)), '')
    if not suffix and data.startswith(b'%PDF-'):
        suffix = '.pdf'
    elif not suffix and data.startswith(b'PK\x03\x04'):
        suffix = '.docx'
    elif not suffix and content_type == 'application/pdf':
        suffix = '.pdf'
    elif not suffix and content_type in {'text/plain', 'text/html'}:
        if content_type == 'text/html':
            raise ValueError('The source returned a web page, not a document file. Use a direct PDF, DOCX, or TXT download URL.')
        suffix = '.txt'
    elif not suffix:
        guessed = mimetypes.guess_extension(content_type or '')
        suffix = guessed if guessed in {'.pdf', '.docx', '.txt'} else ''
    if suffix not in {'.pdf', '.docx', '.txt'}:
        raise ValueError('Unsupported library file. Use a direct PDF, DOCX, or TXT file URL.')
    return f'official-document{suffix}', data

def _section_for_chunk(content: str) -> str | None:
    found = _SECTION.search(content)
    return found.group(0)[:180] if found else None

def ingest_library_document(db: Session, document_id, force: bool = False) -> dict:
    """Index the linked official file and preserve every previous content version."""
    document = db.get(LibraryDocument, document_id)
    if not document:
        return {'status': 'deleted'}
    lock_collection = db.scalar(select(LibraryCollection).where(LibraryCollection.id == document.collection_id).with_for_update())
    if not lock_collection:
        raise ValueError('The document collection no longer exists.')
    failed_record_id = document.id
    document.status = 'processing'
    document.processing_error = None
    db.commit()
    try:
        if document.storage_url and document.original_filename:
            from app.services.storage import download_file
            data = download_file(document.storage_url, LIBRARY_MAX_BYTES)
            filename = document.original_filename
        else:
            filename, data = download_official_file(document.source_url)
        digest = hashlib.sha256(data).hexdigest()
        current = db.scalar(select(LibraryDocument).where(
            LibraryDocument.collection_id == document.collection_id,
            LibraryDocument.short_name == document.short_name,
            LibraryDocument.is_current.is_(True),
        ).with_for_update())
        same_hash = db.scalar(select(LibraryDocument).where(
            LibraryDocument.collection_id == document.collection_id,
            LibraryDocument.short_name == document.short_name,
            LibraryDocument.content_hash == digest,
            LibraryDocument.status == 'ready',
        ).order_by(LibraryDocument.is_current.desc(), LibraryDocument.created_at.desc()).limit(1).with_for_update())
        if same_hash and not force:
            if same_hash.id != document.id:
                was_current = same_hash.is_current
                if current and current.id != same_hash.id:
                    current.is_current = False
                same_hash.is_current = True
                same_hash.updated_at = datetime.now(timezone.utc)
                db.delete(document)
                if not was_current:
                    enqueue_library_update(db, same_hash.collection_id,
                        current.id if current and current.id != same_hash.id else None,
                        same_hash.id, 'restored')
                db.commit()
            else:
                document.status = 'ready'
                db.commit()
            return {'status': 'unchanged', 'document_id': str(same_hash.id), 'content_hash': digest}

        # If an already published version's source now points to new content,
        # add a new immutable version row and leave the old one intact.
        if document.content_hash and document.content_hash != digest:
            replacement = LibraryDocument(
                collection_id=document.collection_id, title=document.title, short_name=document.short_name,
                source_url=document.source_url, publisher=document.publisher,
                original_filename=document.original_filename, storage_url=document.storage_url,
                cloudinary_public_id=document.cloudinary_public_id, cloudinary_resource_type=document.cloudinary_resource_type,
                document_date=document.document_date, version_label=document.version_label,
                effective_from=document.effective_from, status='processing', is_current=False,
            )
            db.add(replacement)
            db.flush()
            document = replacement
            failed_record_id = replacement.id
        extracted = extract_document(filename, data)
        pages = extracted['pages']
        if sum(len(page_text) for _, page_text in pages) > max_extracted_chars():
            raise ValueError(f'Extracted source text exceeds the {max_extracted_chars():,} character limit.')
        passages = chunk_pages(pages)
        if not passages:
            raise ValueError('No readable text was found. Use a text-based PDF, TXT, or DOCX source.')
        db.execute(delete(LibraryChunk).where(LibraryChunk.library_document_id == document.id))
        db.commit()
        for offset in range(0, len(passages), 32):
            batch = passages[offset:offset + 32]
            vectors = [vector for vectors in iter_embedding_batches([content for _, content in batch], batch_size=16) for vector in vectors]
            for local_index, ((page, content), vector) in enumerate(zip(batch, vectors)):
                db.add(LibraryChunk(library_document_id=document.id, chunk_index=offset + local_index,
                    page_number=page, section_title=_section_for_chunk(content), content=content, embedding=vector))
            db.commit()
        current = db.scalar(select(LibraryDocument).where(
            LibraryDocument.collection_id == document.collection_id,
            LibraryDocument.short_name == document.short_name,
            LibraryDocument.is_current.is_(True),
            LibraryDocument.id != document.id,
        ).with_for_update())
        if current:
            current.is_current = False
        document.content_hash = digest
        document.is_current = True
        document.status = 'ready'
        document.chunk_count = len(passages)
        document.page_count = len(pages)
        document.ocr_used = bool(extracted['ocr_used'])
        document.ocr_confidence = extracted['ocr_confidence']
        document.processing_error = None
        document.updated_at = datetime.now(timezone.utc)
        enqueue_library_update(db, document.collection_id, current.id if current else None,
            document.id, 'version' if current else 'added')
        db.commit()
        return {'status': 'ready', 'document_id': str(document.id), 'content_hash': digest, 'chunk_count': len(passages)}
    except Exception as exc:
        db.rollback()
        failed = db.get(LibraryDocument, failed_record_id)
        if failed:
            failed.status = 'failed'
            failed.processing_error = (str(exc) or 'Library ingestion failed.')[:500]
            db.commit()
        logger.exception('Official library ingestion failed for record %s.', document_id)
        raise

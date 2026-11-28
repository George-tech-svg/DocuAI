"""Read-only member endpoints and administrator-only shared library management."""
from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session
from app.api.dependencies import current_user, admin_user
from app.db.session import get_db
from app.models.entities import LibraryCollection, LibraryDocument, LibraryChunk, LibraryUpdate
from app.models.user import User
from app.services.job_queue import enqueue_library_ingest
from starlette.concurrency import run_in_threadpool
from app.services.storage import store_file
from app.services.file_validation import validate_upload

router = APIRouter(prefix='/library', tags=['Kenyan Library'])
admin_router = APIRouter(prefix='/admin/library', tags=['Administration'], dependencies=[Depends(admin_user)])

class CollectionInput(BaseModel):
    slug: str = Field(min_length=2, max_length=100, pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
    name: str = Field(min_length=2, max_length=180)
    description: str = Field(default='', max_length=4000)
    category: str = Field(pattern=r'^(tax|employment|procurement|companies|data-protection|education|courts)$')

class LibraryDocumentInput(BaseModel):
    collection_id: UUID
    title: str = Field(min_length=2, max_length=300)
    short_name: str = Field(min_length=2, max_length=160)
    source_url: HttpUrl
    publisher: str = Field(min_length=2, max_length=200)
    version_label: str = Field(min_length=1, max_length=120)
    document_date: datetime | None = None
    effective_from: datetime | None = None

@router.get('/collections')
def list_collections(_user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(LibraryCollection).order_by(LibraryCollection.category, LibraryCollection.name)).all()
    result = []
    for row in rows:
        count = db.scalar(select(func.count(LibraryDocument.id)).where(LibraryDocument.collection_id == row.id, LibraryDocument.is_current.is_(True), LibraryDocument.status == 'ready')) or 0
        result.append({'id': row.id, 'slug': row.slug, 'name': row.name, 'description': row.description, 'category': row.category, 'ready_document_count': count})
    return result

@router.get('/documents')
def list_documents(_user: User = Depends(current_user), db: Session = Depends(get_db), collection_id: UUID | None = None, q: str | None = None):
    query = select(LibraryDocument, LibraryCollection.name.label('collection_name')).join(LibraryCollection).where(LibraryDocument.is_current.is_(True), LibraryDocument.status == 'ready')
    if collection_id:
        query = query.where(LibraryDocument.collection_id == collection_id)
    if q and q.strip():
        term = f'%{q.strip()}%'
        query = query.where(LibraryDocument.title.ilike(term) | LibraryDocument.short_name.ilike(term) | LibraryDocument.publisher.ilike(term))
    rows = db.execute(query.order_by(LibraryCollection.name, LibraryDocument.title).limit(200)).all()
    return [{'id': doc.id, 'collection_id': doc.collection_id, 'collection_name': collection, 'title': doc.title, 'short_name': doc.short_name, 'publisher': doc.publisher, 'source_url': doc.source_url, 'version_label': doc.version_label, 'document_date': doc.document_date, 'effective_from': doc.effective_from, 'page_count': doc.page_count} for doc, collection in rows]

@router.get('/search')
def search_library(q: str, _user: User = Depends(current_user), db: Session = Depends(get_db), collection_id: UUID | None = None):
    if len(q.strip()) < 2:
        raise HTTPException(422, 'Enter at least two characters to search the library.')
    vector = func.websearch_to_tsquery(literal_column("'simple'"), q)
    query = select(LibraryChunk, LibraryDocument, LibraryCollection.name.label('collection_name')).join(LibraryDocument).join(LibraryCollection).where(
        LibraryDocument.status == 'ready', LibraryDocument.is_current.is_(True),
        func.to_tsvector(literal_column("'simple'"), LibraryChunk.content).op('@@')(vector),
    )
    if collection_id:
        query = query.where(LibraryDocument.collection_id == collection_id)
    rows = db.execute(query.order_by(func.ts_rank_cd(func.to_tsvector(literal_column("'simple'"), LibraryChunk.content), vector).desc()).limit(30)).all()
    return [{'document_id': doc.id, 'collection_id': doc.collection_id, 'title': doc.title, 'version_label': doc.version_label, 'publisher': doc.publisher, 'collection_name': collection, 'page_number': chunk.page_number, 'section_title': chunk.section_title, 'excerpt': chunk.content[:700], 'source_url': doc.source_url} for chunk, doc, collection in rows]

@admin_router.get('/collections')
def admin_collections(_admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(LibraryCollection).order_by(LibraryCollection.category, LibraryCollection.name)).all()
    return [{'id': c.id, 'slug': c.slug, 'name': c.name, 'description': c.description, 'category': c.category} for c in rows]

@admin_router.post('/collections')
def create_collection(data: CollectionInput, _admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    if db.scalar(select(LibraryCollection.id).where(LibraryCollection.slug == data.slug)):
        raise HTTPException(409, 'A collection with this slug already exists.')
    row = LibraryCollection(**data.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    return {'id': row.id, 'slug': row.slug, 'name': row.name, 'category': row.category}

@admin_router.get('/documents')
def admin_documents(_admin: User = Depends(admin_user), db: Session = Depends(get_db), collection_id: UUID | None = None):
    query = select(LibraryDocument, LibraryCollection.name.label('collection_name')).join(LibraryCollection)
    if collection_id: query = query.where(LibraryDocument.collection_id == collection_id)
    rows = db.execute(query.order_by(LibraryDocument.created_at.desc()).limit(500)).all()
    return [{'id': d.id, 'collection_id': d.collection_id, 'collection_name': c, 'title': d.title, 'short_name': d.short_name, 'publisher': d.publisher, 'source_url': d.source_url, 'version_label': d.version_label, 'is_current': d.is_current, 'status': d.status, 'processing_error': d.processing_error, 'content_hash': d.content_hash, 'created_at': d.created_at} for d, c in rows]

@admin_router.get('/documents/{document_id}/versions')
def document_versions(document_id: UUID, _admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    document = db.get(LibraryDocument, document_id)
    if not document: raise HTTPException(404, 'Library document not found.')
    rows = db.scalars(select(LibraryDocument).where(LibraryDocument.collection_id == document.collection_id, LibraryDocument.short_name == document.short_name).order_by(LibraryDocument.created_at.desc())).all()
    return [{'id': d.id, 'title': d.title, 'version_label': d.version_label, 'is_current': d.is_current, 'status': d.status, 'content_hash': d.content_hash, 'created_at': d.created_at} for d in rows]

@admin_router.post('/documents')
def add_document(data: LibraryDocumentInput, _admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    if not db.get(LibraryCollection, data.collection_id): raise HTTPException(404, 'Library collection not found.')
    from app.services.library_ingestion import validate_official_source_url
    try: source_url = validate_official_source_url(str(data.source_url))
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
    doc = LibraryDocument(**{**data.model_dump(exclude={'source_url'}), 'source_url': source_url, 'status': 'queued', 'is_current': False})
    db.add(doc); db.flush(); enqueue_library_ingest(db, doc.id); db.commit(); db.refresh(doc)
    return {'id': doc.id, 'status': doc.status, 'message': 'Official document queued for ingestion.'}

@admin_router.post('/documents/upload', status_code=202)
async def upload_official_document(
    collection_id: UUID = Form(...), title: str = Form(...), short_name: str = Form(...),
    source_url: str = Form(...), publisher: str = Form(...), version_label: str = Form(...),
    file: UploadFile = File(...), _admin: User = Depends(admin_user), db: Session = Depends(get_db),
):
    """Store an administrator-supplied authorized original, then queue indexing."""
    if not db.get(LibraryCollection, collection_id): raise HTTPException(404, 'Library collection not found.')
    from app.services.library_ingestion import validate_official_source_url, LIBRARY_MAX_BYTES
    try: source_url = validate_official_source_url(source_url)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
    data = await file.read(LIBRARY_MAX_BYTES + 1)
    if len(data) > LIBRARY_MAX_BYTES: raise HTTPException(413, 'The library file exceeds the 50 MB ingestion limit.')
    filename, content_type = validate_upload(file.filename or '', data, 50)
    if not filename.lower().endswith(('.pdf', '.txt', '.docx')):
        raise HTTPException(422, 'Library ingestion supports PDF, TXT, or DOCX files.')
    try: stored = await run_in_threadpool(store_file, filename, data)
    except Exception as exc: raise HTTPException(502, 'The library file could not be stored. Please try again.') from exc
    doc = LibraryDocument(collection_id=collection_id, title=title[:300], short_name=short_name[:160], source_url=source_url, publisher=publisher[:200], version_label=version_label[:120], original_filename=filename, storage_url=stored['url'], cloudinary_public_id=stored['public_id'], cloudinary_resource_type=stored['resource_type'], status='queued', is_current=False)
    try:
        db.add(doc); db.flush(); enqueue_library_ingest(db, doc.id); db.commit()
    except Exception as exc:
        db.rollback()
        from app.services.storage import delete_file
        try: await run_in_threadpool(delete_file, stored['public_id'], stored['resource_type'])
        except Exception: pass
        raise HTTPException(500, 'The file was stored but could not be queued for indexing.') from exc
    return {'id': doc.id, 'status': doc.status, 'message': 'Official document uploaded and queued for indexing.'}

@admin_router.post('/documents/{document_id}/reindex')
def reindex_document(document_id: UUID, _admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    doc = db.get(LibraryDocument, document_id)
    if not doc: raise HTTPException(404, 'Library document not found.')
    doc.status = 'queued'; doc.processing_error = None
    enqueue_library_ingest(db, doc.id, force=True); db.commit()
    return {'id': doc.id, 'status': 'queued'}


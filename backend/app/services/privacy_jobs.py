"""Background exports, data deletion, and organization retention enforcement."""
from __future__ import annotations

import json
import os
import re
import tempfile
import textwrap
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings, max_upload_mb
from app.models.entities import (AuditEvent, Conversation, DataDeletionRequest,
    DataExportRequest, Document, Job, KnowledgeBase, Message, Organization, User)
from app.services.storage import delete_file, download_file, store_export_file


def _pdf_bytes(title: str, lines: list[str]) -> bytes:
    """Create a small, valid WinAnsi text PDF without another runtime dependency."""
    rendered = []
    for line in [title, '', *lines]:
        rendered.extend(textwrap.wrap(str(line), width=92, replace_whitespace=False, drop_whitespace=True) or [''])
    pages = [rendered[i:i + 48] for i in range(0, max(1, len(rendered)), 48)]
    objects: list[bytes] = []
    page_ids = [3 + i * 2 for i in range(len(pages))]
    content_ids = [page_id + 1 for page_id in page_ids]
    objects.append(b'<< /Type /Catalog /Pages 2 0 R >>')
    kids = ' '.join(f'{page_id} 0 R' for page_id in page_ids)
    objects.append(f'<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>'.encode())
    for page_id, content_id, page_lines in zip(page_ids, content_ids, pages):
        objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {3 + len(pages) * 2} 0 R >> >> /Contents {content_id} 0 R >>'.encode())
        commands = ['BT', '/F1 10 Tf', '48 744 Td', '14 TL']
        for line in page_lines:
            safe = line.encode('cp1252', errors='replace').decode('cp1252')
            escaped = safe.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
            commands.append(f'({escaped}) Tj')
            commands.append('T*')
        commands.append('ET')
        stream = '\n'.join(commands).encode('cp1252', errors='replace')
        objects.append(b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream')
    objects.append(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>')
    output = bytearray(b'%PDF-1.4\n%DocuMind privacy export\n')
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f'{index} 0 obj\n'.encode() + obj + b'\nendobj\n')
    xref_offset = len(output)
    output.extend(f'xref\n0 {len(objects) + 1}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]: output.extend(f'{offset:010d} 00000 n \n'.encode())
    output.extend(f'trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF'.encode())
    return bytes(output)


def _safe_name(value: str) -> str:
    name = re.sub(r'[^A-Za-z0-9._-]+', '_', Path(value).name).strip('._')
    return name[:150] or 'document'


def _personal_scope(db: Session, user_id: UUID):
    folders = db.scalars(select(KnowledgeBase).where(KnowledgeBase.user_id == user_id,
        KnowledgeBase.organization_id.is_(None))).all()
    folder_ids = [folder.id for folder in folders]
    documents = db.scalars(select(Document).where(Document.knowledge_base_id.in_(folder_ids))).all() if folder_ids else []
    # A user's private conversations remain their personal data even when
    # created while viewing an organization folder. Shared chats belong in the
    # organization export and must not leak into a member's personal archive.
    conversations = db.scalars(select(Conversation).where(Conversation.user_id == user_id,
        Conversation.visibility == 'private').order_by(Conversation.created_at)).all()
    return folders, documents, conversations


def _organization_scope(db: Session, organization_id: UUID, requesting_user_id: UUID | None = None):
    folders = db.scalars(select(KnowledgeBase).where(KnowledgeBase.organization_id == organization_id)).all()
    folder_ids = [folder.id for folder in folders]
    documents = db.scalars(select(Document).where(Document.knowledge_base_id.in_(folder_ids))).all() if folder_ids else []
    query = select(Conversation).where(Conversation.knowledge_base_id.in_(folder_ids)).order_by(Conversation.created_at) if folder_ids else None
    conversations = db.scalars(query).all() if query is not None else []
    # Private organization-folder conversations are personal, not shared org
    # records. Include only the requesting owner's own private conversations.
    conversations = [conv for conv in conversations if conv.visibility == 'shared' or
        (requesting_user_id is not None and conv.user_id == requesting_user_id)]
    return folders, documents, conversations


def build_export_archive(db: Session, export: DataExportRequest, temp_path: str) -> None:
    """Create a ZIP containing only the requested user's or organization's data."""
    if export.organization_id:
        org = db.get(Organization, export.organization_id)
        if not org: raise RuntimeError('The organization was deleted before its export ran.')
        folders, documents, conversations = _organization_scope(db, org.id, export.requested_by_user_id)
        metadata = {'export_scope':'organization','organization':{'id':str(org.id),'name':org.name,'type':org.type},
                    'folders':[{'id':str(kb.id),'name':kb.name,'description':kb.description} for kb in folders]}
    else:
        user = db.get(User, export.owner_user_id) if export.owner_user_id else None
        if not user: raise RuntimeError('The account was deleted before its export ran.')
        folders, documents, conversations = _personal_scope(db, user.id)
        metadata = {'export_scope':'personal','profile':{'id':str(user.id),'name':user.full_name,'email':user.email,
                    'created_at':user.created_at.isoformat()},
                    'folders':[{'id':str(kb.id),'name':kb.name,'description':kb.description} for kb in folders]}
    metadata['documents'] = [{'id':str(doc.id),'folder_id':str(doc.knowledge_base_id),
        'filename':doc.original_filename,'content_type':doc.content_type,'size_bytes':doc.file_size_bytes,
        'status':doc.status,'created_at':doc.created_at.isoformat()} for doc in documents]
    metadata['conversations'] = [{'id':str(conv.id),'title':conv.title,'created_at':conv.created_at.isoformat()} for conv in conversations]
    total_bytes = 0
    max_bytes = get_settings().PRIVACY_EXPORT_MAX_MB * 1_000_000
    with zipfile.ZipFile(temp_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr('data/metadata.json', json.dumps(metadata, ensure_ascii=False, indent=2))
        for doc in documents:
            if not doc.storage_url: continue
            if not doc.storage_url.startswith('https://res.cloudinary.com/'):
                raise RuntimeError('A stored original file URL failed the export security check.')
            original = download_file(doc.storage_url, max_upload_mb() * 1_000_000)
            total_bytes += len(original)
            if total_bytes > max_bytes: raise RuntimeError(f'This archive exceeds the configured {get_settings().PRIVACY_EXPORT_MAX_MB} MB export limit.')
            archive.writestr(f"data/original_files/{doc.id}_{_safe_name(doc.original_filename)}", original)
        for conv in conversations:
            msgs = db.scalars(select(Message).where(Message.conversation_id == conv.id).order_by(Message.message_index, Message.created_at)).all()
            payload = [{'role':m.role,'content':m.content,'created_at':m.created_at.isoformat(),
                'sources':m.sources_json,'metadata':m.metadata_json,'model_version':m.model_name} for m in msgs]
            archive.writestr(f'data/conversations/{conv.id}.json', json.dumps(payload, ensure_ascii=False, indent=2))
            pdf_lines = [f"{m['role'].upper()} — {m['created_at']}" for m in payload for _ in [0]]
            for msg in payload: pdf_lines.extend([f"{msg['role'].upper()}: {msg['content']}", ''])
            archive.writestr(f'data/conversations/{conv.id}.pdf', _pdf_bytes(conv.title, pdf_lines))
    if os.path.getsize(temp_path) > max_bytes:
        raise RuntimeError(f'This archive exceeds the configured {get_settings().PRIVACY_EXPORT_MAX_MB} MB export limit.')


def process_export(db: Session, export_id: UUID) -> None:
    export = db.get(DataExportRequest, export_id)
    if not export or export.status == 'ready': return
    export.status = 'processing'; export.error = None; db.commit()
    public_id = str(export.id)
    try:
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as handle:
            temp_path = handle.name
        try:
            build_export_archive(db, export, temp_path)
            store_export_file(temp_path, public_id)
        finally:
            try: os.unlink(temp_path)
            except OSError: pass
        export.storage_public_id = public_id
        export.status = 'ready'; export.completed_at = datetime.now(timezone.utc)
        export.expires_at = export.completed_at + timedelta(days=7)
        db.add(AuditEvent(organization_id=export.organization_id, actor_user_id=export.requested_by_user_id,
            action='data_export_ready', resource_type='data_export', resource_id=str(export.id), details={'scope':'organization' if export.organization_id else 'personal'}))
        db.commit()
    except Exception as exc:
        db.rollback()
        current = db.get(DataExportRequest, export_id)
        if current:
            current.status = 'failed'; current.error = str(exc)[:500]; db.commit()
        raise


def _delete_documents_from_cloudinary(documents) -> None:
    for document in documents:
        if document.cloudinary_public_id:
            delete_file(document.cloudinary_public_id, document.cloudinary_resource_type or 'raw')
        elif document.storage_url:
            raise RuntimeError('A stored original is missing its Cloudinary asset ID; cleanup needs administrator review.')


def process_deletion(db: Session, deletion_id: UUID) -> None:
    request = db.get(DataDeletionRequest, deletion_id)
    if not request or request.status == 'done': return
    request.status = 'processing'; request.error = None; db.commit()
    try:
        if request.target_type == 'account':
            user = db.get(User, request.target_id)
            if not user:
                request.status = 'done'; request.completed_at = datetime.now(timezone.utc); db.commit(); return
            folders, documents, _ = _personal_scope(db, user.id)
            # Account deletion removes the user's personal originals only.
            # Organization originals remain attached to their shared folders.
            _delete_documents_from_cloudinary(documents)
            # Organization folders are owned by the organization; reassign their
            # legacy required user_id to the recorded organization creator first.
            for folder in db.scalars(select(KnowledgeBase).where(KnowledgeBase.user_id == user.id,
                    KnowledgeBase.organization_id.is_not(None))).all():
                organization = db.get(Organization, folder.organization_id)
                creator = db.get(User, organization.created_by) if organization else None
                if creator:
                    # Set the relationship as well as the FK so the account's
                    # delete-orphan collection does not remove shared folders.
                    folder.user = creator
            # A shared organization conversation is workspace content. Transfer
            # its owner to the organization creator before deleting this user;
            # private conversations are still removed with the account.
            shared_org_conversations = db.scalars(select(Conversation).join(KnowledgeBase,
                KnowledgeBase.id == Conversation.knowledge_base_id).where(
                Conversation.user_id == user.id, Conversation.visibility == 'shared',
                KnowledgeBase.organization_id.is_not(None))).all()
            for conversation in shared_org_conversations:
                organization = db.get(Organization, conversation.knowledge_base.organization_id)
                creator = db.get(User, organization.created_by) if organization else None
                if creator:
                    conversation.user = creator
            for export in db.scalars(select(DataExportRequest).where(
                    (DataExportRequest.owner_user_id == user.id) | (DataExportRequest.requested_by_user_id == user.id))).all():
                if export.storage_public_id: delete_file(export.storage_public_id, 'raw', asset_type='authenticated')
                export.status, export.storage_public_id = 'expired', None
            db.add(AuditEvent(organization_id=None, actor_user_id=None, action='account_data_deleted',
                resource_type='deletion_request', resource_id=str(request.id), details={'request_id':str(request.id)}))
            request.status = 'done'; request.completed_at = datetime.now(timezone.utc)
            # Retain completion evidence without keeping a direct lookup from
            # this operational request row to the erased account UUID.
            request.target_id = uuid4()
            db.delete(user); db.commit()
        else:
            org = db.get(Organization, request.target_id)
            if not org:
                request.status = 'done'; request.completed_at = datetime.now(timezone.utc); db.commit(); return
            _folders, documents, _conversations = _organization_scope(db, org.id)
            _delete_documents_from_cloudinary(documents)
            for export in db.scalars(select(DataExportRequest).where(DataExportRequest.organization_id == org.id)).all():
                if export.storage_public_id: delete_file(export.storage_public_id, 'raw', asset_type='authenticated')
                export.status, export.storage_public_id = 'expired', None
            db.add(AuditEvent(organization_id=org.id, actor_user_id=request.requested_by_user_id,
                action='organization_data_deleted', resource_type='organization', resource_id=str(org.id),
                details={'name':org.name,'request_id':str(request.id)}))
            request.status = 'done'; request.completed_at = datetime.now(timezone.utc)
            db.delete(org); db.commit()
    except Exception as exc:
        db.rollback()
        current = db.get(DataDeletionRequest, deletion_id)
        if current:
            current.status = 'failed'; current.error = str(exc)[:500]; db.commit()
        raise


def enforce_organization_retention(db: Session, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    organizations = db.scalars(select(Organization).where(Organization.retention_days.is_not(None))).all()
    removed = 0
    for org in organizations:
        cutoff = now - timedelta(days=org.retention_days)
        folders = db.scalars(select(KnowledgeBase).where(KnowledgeBase.organization_id == org.id)).all()
        for folder in folders:
            docs = db.scalars(select(Document).where(Document.knowledge_base_id == folder.id, Document.created_at < cutoff)).all()
            for doc in docs:
                try:
                    if doc.cloudinary_public_id: delete_file(doc.cloudinary_public_id, doc.cloudinary_resource_type or 'raw')
                    db.add(AuditEvent(organization_id=org.id, actor_user_id=None, action='retention_document_deleted',
                        resource_type='document', resource_id=str(doc.id), details={'filename':doc.original_filename,'retention_days':org.retention_days}))
                    db.delete(doc); db.commit(); removed += 1
                except Exception:
                    db.rollback()
            old_chats = db.scalars(select(Conversation).where(Conversation.knowledge_base_id == folder.id,
                Conversation.created_at < cutoff)).all()
            for conv in old_chats:
                db.add(AuditEvent(organization_id=org.id, actor_user_id=None, action='retention_conversation_deleted',
                    resource_type='conversation', resource_id=str(conv.id), details={'retention_days':org.retention_days}))
                db.delete(conv); removed += 1
        db.commit()
    return removed


def cleanup_expired_exports(db: Session, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    rows = db.scalars(select(DataExportRequest).where(DataExportRequest.status == 'ready', DataExportRequest.expires_at <= now)).all()
    for row in rows:
        if row.storage_public_id:
            delete_file(row.storage_public_id, 'raw', asset_type='authenticated')
        row.storage_public_id = None; row.status = 'expired'; row.error = None
    db.commit()
    return len(rows)

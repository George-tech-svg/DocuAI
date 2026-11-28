"""Long-lived Render worker for durable document indexing jobs."""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy.orm import sessionmaker
from app.db.session import get_engine
from app.models.entities import Document, Job, KnowledgeBase
from app.services.document_service import process_upload
from app.services.job_queue import claim_next_job, complete_job, fail_job, heartbeat, enqueue_extract_events, enqueue_reminder_minute
from app.services.storage import download_file
from app.core.config import max_upload_mb

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger('documind.worker')
SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
WORKER_ID = f'{socket.gethostname()}-{uuid4()}'
POLL_SECONDS = max(1, int(os.getenv('JOB_POLL_SECONDS', '3')))
MAX_BYTES = max_upload_mb() * 1_000_000


def safe_job_error(error: Exception) -> str:
    detail = getattr(error, 'detail', None)
    if isinstance(detail, str) and 0 < len(detail) <= 500:
        return detail
    if isinstance(error, (ValueError, RuntimeError)):
        message = str(error).strip()
        if message and len(message) <= 500 and '\n' not in message:
            return message
    return 'We could not process this file. Please check that it is valid and try again.'


def _heartbeat_loop(job_id: UUID, stop: threading.Event):
    while not stop.wait(60):
        try:
            with SessionLocal() as db:
                if not heartbeat(db, job_id, WORKER_ID):
                    logger.warning('Lost lock for job %s', job_id)
                    return
        except Exception:
            logger.exception('Could not refresh job lock for %s', job_id)


def run_job(job: Job):
    job_id = job.id
    payload = job.payload if isinstance(job.payload, dict) else {}
    document_id = payload.get('document_id')
    if job.type == 'ingest_library_document':
        from app.services.library_ingestion import ingest_library_document
        with SessionLocal() as db:
            ingest_library_document(db, UUID(str(payload['library_document_id'])), force=bool(payload.get('force')))
        return
    if job.type == 'record_library_update':
        from app.models.entities import LibraryUpdate
        from sqlalchemy import select
        with SessionLocal() as db:
            new_id = UUID(str(payload['new_document_id']))
            exists = db.scalar(select(LibraryUpdate.id).where(LibraryUpdate.new_document_id == new_id).limit(1))
            if not exists:
                db.add(LibraryUpdate(collection_id=UUID(str(payload['collection_id'])), previous_document_id=UUID(str(payload['previous_document_id'])) if payload.get('previous_document_id') else None, new_document_id=new_id, change_kind=payload.get('change_kind', 'added')))
                db.commit()
        return
    if job.type == 'extract_events' and document_id:
        from app.services.event_extraction import extract_events_for_document
        from app.models.entities import WhatsAppDocumentUpload
        with SessionLocal() as db:
            extract_events_for_document(db, UUID(str(document_id)))
            upload = db.scalar(__import__('sqlalchemy').select(WhatsAppDocumentUpload).where(WhatsAppDocumentUpload.document_id == UUID(str(document_id))))
            if upload:
                db.add(Job(type='whatsapp_document_ready', payload={'document_id': str(document_id)}, max_attempts=4))
                db.commit()
        return
    if job.type == 'whatsapp_document_ready':
        from app.services.whatsapp_jobs import notify_document_ready
        with SessionLocal() as db:
            notify_document_ready(db, UUID(str(payload['document_id'])))
        return
    if job.type == 'whatsapp_document_failed':
        from app.services.whatsapp_jobs import notify_document_failed
        with SessionLocal() as db:
            notify_document_failed(db, UUID(str(payload['document_id'])))
        return
    if job.type == 'sync_whatsapp_usage':
        from app.services.reminders import reconcile_whatsapp_usage
        with SessionLocal() as db:
            reconcile_whatsapp_usage(db)
        return
    if job.type == 'export_user_data' or job.type == 'export_organization_data':
        from app.services.privacy_jobs import process_export
        with SessionLocal() as db:
            process_export(db, UUID(str(payload['export_id'])))
        return
    if job.type == 'delete_user_data' or job.type == 'delete_organization_data':
        from app.services.privacy_jobs import process_deletion
        with SessionLocal() as db:
            process_deletion(db, UUID(str(payload['deletion_id'])))
        return
    if job.type == 'enforce_organization_retention':
        from app.services.privacy_jobs import enforce_organization_retention
        with SessionLocal() as db:
            enforce_organization_retention(db)
        return
    if job.type == 'cleanup_privacy_exports':
        from app.services.privacy_jobs import cleanup_expired_exports
        with SessionLocal() as db:
            cleanup_expired_exports(db)
        return
    if job.type == 'send_due_reminders':
        from app.services.reminders import send_due_reminders
        with SessionLocal() as db:
            send_due_reminders(db)
        return
    if job.type == 'process_whatsapp_message':
        from app.services.whatsapp_jobs import process_whatsapp_message
        with SessionLocal() as db:
            process_whatsapp_message(db, UUID(str(payload['message_id'])))
        return
    if job.type != 'index_document' or not document_id:
        raise ValueError('This processing job is not supported.')
    with SessionLocal() as db:
        document = db.get(Document, UUID(str(document_id)))
        if document is None:
            return
        if document.status == 'ready':
            enqueue_extract_events(db, document.id)
            db.commit()
            return
        kb = db.get(KnowledgeBase, document.knowledge_base_id)
        if kb is None:
            return
        if not document.storage_url:
            raise RuntimeError('The stored original file could not be found. Please upload the file again.')
        document.status = 'processing'
        document.progress_stage = 'extracting'
        document.updated_at = datetime.now(timezone.utc)
        db.commit()
        file_url = document.storage_url
        filename = document.original_filename
        kb_id = document.knowledge_base_id
        user_id = kb.user_id
        document_uuid = document.id
    data = download_file(file_url, MAX_BYTES)
    with SessionLocal() as db:
        result = process_upload(db, user_id, kb_id, filename, data, document_id=document_uuid, raise_on_error=True)
        if result is None:
            logger.info('Document %s was deleted before its job ran.', document_uuid)
        elif result.status == 'ready':
            enqueue_extract_events(db, document_uuid)
            db.commit()


def process_one() -> bool:
    with SessionLocal() as db:
        job = claim_next_job(db, WORKER_ID)
    if job is None:
        return False
    job_id = job.id
    stop_heartbeat = threading.Event()
    heartbeat_thread = threading.Thread(target=_heartbeat_loop, args=(job_id, stop_heartbeat), daemon=True)
    heartbeat_thread.start()
    logger.info('Claimed job %s (%s), attempt %s/%s.', job_id, job.type, job.attempts, job.max_attempts)
    try:
        run_job(job)
        with SessionLocal() as db:
            complete_job(db, job_id, WORKER_ID)
        logger.info('Completed job %s.', job_id)
    except Exception as exc:
        safe_error = safe_job_error(exc)
        logger.exception('Job %s failed: %s', job_id, safe_error)
        with SessionLocal() as db:
            result = fail_job(db, job_id, WORKER_ID, safe_error)
            if result == 'failed' and job.type == 'index_document' and document_id:
                from app.models.entities import WhatsAppDocumentUpload
                if db.scalar(__import__('sqlalchemy').select(WhatsAppDocumentUpload.id).where(WhatsAppDocumentUpload.document_id == UUID(str(document_id)))):
                    db.add(Job(type='whatsapp_document_failed', payload={'document_id': str(document_id)}, max_attempts=3))
                    db.commit()
        logger.warning('Job %s result after error: %s.', job_id, result)
    finally:
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=1)
    return True


def main():
    logger.info('Starting durable document worker %s.', WORKER_ID)
    last_schedule_minute = None
    last_usage_sync = None
    last_privacy_day = None
    while True:
        try:
            current_minute = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            if current_minute != last_schedule_minute:
                with SessionLocal() as db:
                    enqueue_reminder_minute(db, current_minute)
                last_schedule_minute = current_minute
            if last_usage_sync is None or (datetime.now(timezone.utc) - last_usage_sync).total_seconds() >= 600:
                with SessionLocal() as db:
                    db.add(Job(type='sync_whatsapp_usage', payload={'requested_at': datetime.now(timezone.utc).isoformat()}, max_attempts=3))
                    db.commit()
                last_usage_sync = datetime.now(timezone.utc)
            if current_minute.date() != last_privacy_day:
                with SessionLocal() as db:
                    db.add(Job(type='enforce_organization_retention', payload={'scheduled_at':current_minute.isoformat()}, max_attempts=3))
                    db.add(Job(type='cleanup_privacy_exports', payload={'scheduled_at':current_minute.isoformat()}, max_attempts=3))
                    db.commit()
                last_privacy_day = current_minute.date()
            if not process_one():
                time.sleep(POLL_SECONDS)
        except KeyboardInterrupt:
            logger.info('Worker shutdown requested.')
            return
        except Exception:
            logger.exception('Worker poll failed; will retry.')
            time.sleep(POLL_SECONDS)


if __name__ == '__main__':
    main()

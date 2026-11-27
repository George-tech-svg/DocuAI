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
    if job.type == 'extract_events' and document_id:
        from app.services.event_extraction import extract_events_for_document
        with SessionLocal() as db:
            extract_events_for_document(db, UUID(str(document_id)))
        return
    if job.type == 'send_due_reminders':
        from app.services.reminders import send_due_reminders
        with SessionLocal() as db:
            send_due_reminders(db)
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
        logger.warning('Job %s result after error: %s.', job_id, result)
    finally:
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=1)
    return True


def main():
    logger.info('Starting durable document worker %s.', WORKER_ID)
    last_schedule_minute = None
    while True:
        try:
            current_minute = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            if current_minute != last_schedule_minute:
                with SessionLocal() as db:
                    enqueue_reminder_minute(db, current_minute)
                last_schedule_minute = current_minute
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

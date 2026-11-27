"""PostgreSQL-backed durable jobs with row-lock claiming and bounded retries."""

from datetime import datetime, timedelta, timezone
from uuid import UUID
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from app.models.entities import Document, Job
from sqlalchemy import text

LEASE = timedelta(minutes=10)
MAX_BACKOFF_SECONDS = 6 * 60 * 60


def enqueue_index_document(db: Session, document_id: UUID) -> Job:
    job = Job(type='index_document', payload={'document_id': str(document_id)})
    db.add(job)
    db.flush()
    return job

def enqueue_extract_events(db: Session, document_id: UUID) -> Job | None:
    exists = db.scalar(select(Job.id).where(Job.type == 'extract_events', Job.payload['document_id'].astext == str(document_id), Job.status.in_(['queued', 'running', 'done'])).limit(1))
    if exists:
        return None
    job = Job(type='extract_events', payload={'document_id': str(document_id)})
    db.add(job)
    db.flush()
    return job

def enqueue_reminder_minute(db: Session, now: datetime | None = None) -> Job | None:
    """One scheduler tick per UTC minute, even when multiple worker processes run."""
    now = now or datetime.now(timezone.utc)
    minute = now.replace(second=0, microsecond=0)
    db.execute(text('SELECT pg_advisory_xact_lock(741902113)'))
    exists = db.scalar(select(Job.id).where(Job.type == 'send_due_reminders', Job.payload['minute'].astext == minute.isoformat(), Job.status.in_(['queued', 'running', 'done'])).limit(1))
    if exists:
        db.commit()
        return None
    job = Job(type='send_due_reminders', payload={'minute': minute.isoformat()}, run_after=minute)
    db.add(job)
    db.commit()
    return job


def claim_next_job(db: Session, worker_id: str, now: datetime | None = None) -> Job | None:
    now = now or datetime.now(timezone.utc)
    expired_before = now - LEASE
    # A worker that died on its last allowed attempt must be made terminal.
    exhausted = db.scalars(
        select(Job).where(
            Job.status == 'running', Job.locked_at < expired_before,
            Job.attempts >= Job.max_attempts,
        ).with_for_update(skip_locked=True).limit(20)
    ).all()
    for job in exhausted:
        job.status = 'failed'
        job.locked_at = None
        job.locked_by = None
        job.last_error = 'The worker stopped during the final processing attempt. Please retry this document.'
        _set_document_failure(db, job, job.last_error)

    job = db.scalar(
        select(Job).where(
            Job.attempts < Job.max_attempts,
            or_(
                (Job.status == 'queued') & (Job.run_after <= now),
                (Job.status == 'running') & (Job.locked_at < expired_before),
            ),
        ).order_by(Job.run_after, Job.created_at).with_for_update(skip_locked=True).limit(1)
    )
    if job is None:
        db.commit()
        return None
    job.status = 'running'
    job.attempts += 1
    job.locked_at = now
    job.locked_by = worker_id
    job.updated_at = now
    db.commit()
    db.refresh(job)
    return job


def heartbeat(db: Session, job_id: UUID, worker_id: str, now: datetime | None = None) -> bool:
    job = db.scalar(select(Job).where(Job.id == job_id, Job.status == 'running', Job.locked_by == worker_id))
    if not job:
        db.rollback()
        return False
    job.locked_at = now or datetime.now(timezone.utc)
    job.updated_at = job.locked_at
    db.commit()
    return True


def complete_job(db: Session, job_id: UUID, worker_id: str) -> None:
    job = db.scalar(select(Job).where(Job.id == job_id, Job.locked_by == worker_id))
    if job:
        job.status = 'done'
        job.locked_at = None
        job.locked_by = None
        job.last_error = None
        job.updated_at = datetime.now(timezone.utc)
    db.commit()


def fail_job(db: Session, job_id: UUID, worker_id: str, safe_error: str, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    job = db.scalar(select(Job).where(Job.id == job_id, Job.locked_by == worker_id, Job.status == 'running'))
    if not job:
        db.rollback()
        return 'lost'
    job.last_error = safe_error[:500]
    job.locked_at = None
    job.locked_by = None
    job.updated_at = now
    if job.attempts >= job.max_attempts:
        job.status = 'failed'
        _set_document_failure(db, job, job.last_error)
        outcome = 'failed'
    else:
        delay = min(30 * (2 ** max(job.attempts - 1, 0)), MAX_BACKOFF_SECONDS)
        job.status = 'queued'
        job.run_after = now + timedelta(seconds=delay)
        document_id = job.payload.get('document_id') if isinstance(job.payload, dict) else None
        if document_id and job.type == 'index_document':
            document = db.get(Document, document_id)
            if document:
                document.status = 'pending'
                document.processing_error = job.last_error
                document.updated_at = now
        outcome = 'queued'
    db.commit()
    return outcome


def _set_document_failure(db: Session, job: Job, message: str) -> None:
    if job.type != 'index_document':
        return
    document_id = job.payload.get('document_id') if isinstance(job.payload, dict) else None
    if not document_id:
        return
    document = db.get(Document, document_id)
    if document:
        document.status = 'failed'
        document.processing_error = message[:500]
        document.updated_at = datetime.now(timezone.utc)

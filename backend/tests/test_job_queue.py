from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

from app.models.entities import Job
from app.services import job_queue


class FakeRows:
    def all(self):
        return []


class FakeDb:
    def __init__(self, job=None):
        self.job = job
        self.statements = []
        self.commits = 0

    def scalars(self, statement):
        self.statements.append(statement)
        return FakeRows()

    def scalar(self, statement):
        self.statements.append(statement)
        return self.job

    def get(self, model, identity):
        return None

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        return None

    def rollback(self):
        return None


def test_job_claim_is_atomic_and_uses_skip_locked():
    now = datetime.now(timezone.utc)
    job = SimpleNamespace(
        id='job-1', type='index_document', payload={}, status='queued', attempts=0,
        max_attempts=4, run_after=now, locked_at=None, locked_by=None,
        updated_at=now,
    )
    db = FakeDb(job)

    claimed = job_queue.claim_next_job(db, 'worker-a', now)

    assert claimed is job
    assert job.status == 'running'
    assert job.attempts == 1
    assert job.locked_by == 'worker-a'
    assert db.commits == 1
    postgres_queries = [str(query.compile(dialect=postgresql.dialect())) for query in db.statements]
    assert any('FOR UPDATE SKIP LOCKED' in query for query in postgres_queries)


def test_job_failure_is_requeued_with_exponential_backoff():
    now = datetime.now(timezone.utc)
    job = SimpleNamespace(
        id='job-2', payload={}, status='running', attempts=2, max_attempts=4,
        locked_by='worker-a', locked_at=now, last_error=None, updated_at=now,
        run_after=now,
    )
    db = FakeDb(job)

    outcome = job_queue.fail_job(db, job.id, 'worker-a', 'A readable failure.', now)

    assert outcome == 'queued'
    assert job.status == 'queued'
    assert job.last_error == 'A readable failure.'
    assert job.run_after == now + timedelta(seconds=60)
    assert job.locked_by is None


def test_final_job_failure_becomes_terminal_and_does_not_retry():
    now = datetime.now(timezone.utc)
    job = SimpleNamespace(
        id='job-3', payload={}, status='running', attempts=4, max_attempts=4,
        locked_by='worker-a', locked_at=now, last_error=None, updated_at=now,
        run_after=now,
    )
    db = FakeDb(job)

    outcome = job_queue.fail_job(db, job.id, 'worker-a', 'The document is damaged.', now)

    assert outcome == 'failed'
    assert job.status == 'failed'
    assert job.last_error == 'The document is damaged.'

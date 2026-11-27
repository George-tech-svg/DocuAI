from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.event_extraction import parse_event_date, parse_quoted_calendar_date, resolve_relative_date
from app.services.reminders import _quiet_end
from app.services.job_queue import enqueue_reminder_minute


def test_event_date_parser_requires_iso_calendar_date():
    assert parse_event_date('2030-04-18') == datetime(2030, 4, 18, 12, tzinfo=timezone.utc)
    assert parse_event_date('not a date') is None


def test_relative_date_requires_a_quoted_base_and_resolves_day_count():
    assert resolve_relative_date('14 days after the effective date', 'Effective date: 18 April 2030') == parse_quoted_calendar_date('18 April 2030') + timedelta(days=14)
    assert resolve_relative_date('next month', 'Effective date: 18 April 2030') is None


def test_quiet_hours_respect_nairobi_timezone_and_midnight_crossing():
    preferences = SimpleNamespace(quiet_start='22:00', quiet_end='07:00', timezone='Africa/Nairobi')
    now = datetime(2030, 4, 18, 20, 30, tzinfo=timezone.utc)  # 23:30 in Nairobi
    quiet_end = _quiet_end(now, preferences)
    assert quiet_end == datetime(2030, 4, 19, 4, 0, tzinfo=timezone.utc)


def test_quiet_hours_return_none_outside_window():
    preferences = SimpleNamespace(quiet_start='22:00', quiet_end='07:00', timezone='Africa/Nairobi')
    now = datetime(2030, 4, 18, 8, 0, tzinfo=timezone.utc)  # 11:00 in Nairobi
    assert _quiet_end(now, preferences) is None


def test_reminder_tick_enqueue_is_idempotent_for_a_utc_minute():
    class FakeDb:
        def __init__(self):
            self.results = [None, 'existing-job']
            self.jobs = []
            self.lock_calls = 0
            self.commits = 0
        def execute(self, statement):
            self.lock_calls += 1
        def scalar(self, statement):
            return self.results.pop(0)
        def add(self, item):
            self.jobs.append(item)
        def commit(self):
            self.commits += 1

    db = FakeDb()
    now = datetime(2030, 4, 18, 10, 32, 48, tzinfo=timezone.utc)
    first = enqueue_reminder_minute(db, now)
    second = enqueue_reminder_minute(db, now.replace(second=5))
    assert first is not None
    assert first.payload['minute'] == '2030-04-18T10:32:00+00:00'
    assert second is None
    assert len(db.jobs) == 1
    assert db.lock_calls == 2

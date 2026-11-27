"""Notification channel adapters and idempotent reminder dispatch."""
from datetime import datetime, time, timedelta, timezone
from email.message import EmailMessage
import os
import smtplib
import ssl
from typing import Protocol
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.entities import DocumentEvent, NotificationPreference, Reminder, User

class NotificationChannel(Protocol):
    name: str
    def send(self, user: User, event: DocumentEvent, idempotency_key: str) -> None: ...

class SMTPEmailChannel:
    name = 'email'
    def send(self, user: User, event: DocumentEvent, idempotency_key: str) -> None:
        host = os.getenv('SMTP_HOST', '').strip()
        if not host:
            raise RuntimeError('Email reminders are not configured. Add SMTP_HOST and SMTP credentials to the backend environment.')
        message = EmailMessage()
        message['Subject'] = f'Reminder: {event.title}'
        message['From'] = os.getenv('SMTP_FROM', os.getenv('SMTP_USER', ''))
        message['To'] = user.email
        message['Message-ID'] = f'<reminder-{idempotency_key}@documind.local>'
        message.set_content(f"DocuMind reminder\n\n{event.title}\nDue: {event.due_at.isoformat()}\n\nSource: {event.source_excerpt}\nPage: {event.source_page or 'not available'}\n\nCheck this date against the original document.")
        port = int(os.getenv('SMTP_PORT', '587'))
        with smtplib.SMTP(host, port, timeout=15) as client:
            if os.getenv('SMTP_STARTTLS', 'true').lower() in {'1', 'true', 'yes'}:
                client.starttls(context=ssl.create_default_context())
            username = os.getenv('SMTP_USER', '')
            password = os.getenv('SMTP_PASSWORD', '')
            if username:
                client.login(username, password)
            client.send_message(message)

CHANNELS: dict[str, NotificationChannel] = {'email': SMTPEmailChannel()}

def _quiet_end(now: datetime, preference: NotificationPreference) -> datetime | None:
    if not preference.quiet_start or not preference.quiet_end:
        return None
    zone = ZoneInfo(preference.timezone or 'Africa/Nairobi')
    local = now.astimezone(zone)
    start = time.fromisoformat(preference.quiet_start)
    end = time.fromisoformat(preference.quiet_end)
    if start == end:
        return None
    current = local.timetz().replace(tzinfo=None)
    quiet = (start <= current < end) if start < end else (current >= start or current < end)
    if not quiet:
        return None
    end_date = local.date() + (timedelta(days=1) if start >= end and current >= start else timedelta())
    return datetime.combine(end_date, end, zone).astimezone(timezone.utc)

def send_due_reminders(db: Session, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    sent = 0
    rows = db.scalars(select(Reminder).where(
        Reminder.remind_at <= now,
        Reminder.status.in_(['scheduled', 'failed']),
        (Reminder.next_attempt_at.is_(None) | (Reminder.next_attempt_at <= now)),
    ).order_by(Reminder.remind_at).with_for_update(skip_locked=True).limit(100)).all()
    for reminder in rows:
        event = db.get(DocumentEvent, reminder.event_id)
        if not event or event.status != 'confirmed':
            reminder.status = 'cancelled'
            db.commit()
            continue
        pref = db.get(NotificationPreference, reminder.user_id)
        if pref:
            quiet_end = _quiet_end(now, pref)
            if quiet_end:
                reminder.remind_at = quiet_end
                reminder.status = 'scheduled'
                reminder.error = None
                reminder.next_attempt_at = None
                db.commit()
                continue
            if not (pref.channels or {}).get(reminder.channel, False):
                reminder.status = 'cancelled'
                db.commit()
                continue
        user = db.get(User, reminder.user_id)
        if not user:
            reminder.status = 'cancelled'
            db.commit()
            continue
        try:
            if reminder.channel == 'in_app':
                # The reminder row is itself the durable in-app notification.
                pass
            else:
                adapter = CHANNELS.get(reminder.channel)
                if adapter is None:
                    raise RuntimeError(f'The {reminder.channel} reminder channel is not available.')
                adapter.send(user, event, str(reminder.id))
            reminder.status = 'sent'
            reminder.sent_at = now
            reminder.error = None
            reminder.next_attempt_at = None
            sent += 1
        except Exception as exc:
            reminder.attempts += 1
            reminder.status = 'failed'
            reminder.error = (str(exc) or 'Reminder delivery failed.')[:500]
            reminder.next_attempt_at = now + timedelta(minutes=min(5 * (2 ** (reminder.attempts - 1)), 360))
        db.commit()
    return sent

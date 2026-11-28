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
from app.models.entities import WhatsAppLink, WhatsAppMessage, MessageUsage
from app.services.whatsapp_provider import provider_from_env

class NotificationChannel(Protocol):
    name: str
    def send(self, db: Session, user: User, event: DocumentEvent, idempotency_key: str) -> None: ...

class SMTPEmailChannel:
    name = 'email'
    def send(self, db: Session, user: User, event: DocumentEvent, idempotency_key: str) -> None:
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

class BirdWhatsAppChannel:
    name = 'whatsapp'
    def send(self, db: Session, user: User, event: DocumentEvent, idempotency_key: str) -> None:
        from app.core.config import get_settings
        from app.models.entities import Document, WhatsAppLink, WhatsAppMessage, MessageUsage
        from sqlalchemy import select
        link = db.get(WhatsAppLink, user.id)
        if not link or not link.active or not link.opted_in_at or link.opted_out_at:
            raise RuntimeError('WhatsApp reminders require a linked number with current opt-in.')
        document = db.get(Document, event.document_id)
        body = f'Reminder: {event.title}\nDue: {event.due_at:%d %b %Y}\nSource: {document.original_filename if document else "Document"}, page {event.source_page or "?"}. Check this date against the original document.'
        inbound_recent = bool(link.last_inbound_at and (datetime.now(timezone.utc) - link.last_inbound_at) <= timedelta(hours=24))
        provider = provider_from_env()
        if inbound_recent:
            response = provider.send_text(link.phone_e164, body[:1200], f'reminder-{idempotency_key}')
        else:
            slug = get_settings().BIRD_WHATSAPP_REMINDER_TEMPLATE_SLUG.strip()
            if not slug:
                raise RuntimeError('WhatsApp reminder template is not configured. Set BIRD_WHATSAPP_REMINDER_TEMPLATE_SLUG after Bird/Meta approval.')
            response = provider.send_template(link.phone_e164, slug, 'en', {'title': event.title, 'date': event.due_at.strftime('%d %b %Y'), 'document': document.original_filename if document else 'Document', 'page': event.source_page or 'unknown'}, f'reminder-{idempotency_key}')
        payload = response.get('data', response)
        provider_id = str(payload.get('id') or payload.get('whatsapp_id') or '') or None
        outgoing = WhatsAppMessage(provider_message_id=provider_id, user_id=user.id, phone_e164=link.phone_e164,
            direction='outbound', kind='template' if not inbound_recent else 'text', text=body,
            status='sent', provider_payload=response, idempotency_key=f'reminder-{idempotency_key}')
        db.add(outgoing); db.flush()
        db.add(MessageUsage(whatsapp_message_id=outgoing.id, user_id=user.id, provider_message_id=provider_id, units=1, cost_status='pending' if provider_id else 'unknown'))

CHANNELS: dict[str, NotificationChannel] = {'email': SMTPEmailChannel(), 'whatsapp': BirdWhatsAppChannel()}

def _create_reminders(db: Session, event: DocumentEvent, pref: NotificationPreference) -> None:
    """Create or refresh scheduled reminders without violating the unique key.

    Cancelled rows remain in the database and still participate in the unique
    constraint, so matching rows are reactivated instead of inserted again.
    Sent reminders are kept as history and are not sent a second time.
    """
    now = datetime.now(timezone.utc)
    channels = pref.channels or {'in_app': True}
    desired: dict[tuple[str, datetime], None] = {}
    for raw_days in pref.lead_days or [14, 7, 1]:
        try:
            days = int(raw_days)
        except (TypeError, ValueError):
            continue
        if not 0 <= days <= 365:
            continue
        remind_at = event.due_at - timedelta(days=days)
        if remind_at <= now:
            continue
        for channel in ('in_app', 'email', 'whatsapp'):
            if channels.get(channel, channel == 'in_app'):
                desired[(channel, remind_at)] = None

    existing = db.scalars(select(Reminder).where(Reminder.event_id == event.id)).all()
    for reminder in existing:
        key = (reminder.channel, reminder.remind_at)
        if key in desired:
            desired.pop(key)
            if reminder.status in {'cancelled', 'failed'}:
                reminder.status = 'scheduled'
                reminder.sent_at = None
                reminder.error = None
                reminder.next_attempt_at = None
        elif reminder.status in {'scheduled', 'failed'}:
            reminder.status = 'cancelled'
            reminder.error = None
            reminder.next_attempt_at = None

    for channel, remind_at in desired:
        db.add(Reminder(event_id=event.id, user_id=event.user_id, channel=channel,
            remind_at=remind_at, status='scheduled'))

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
                adapter.send(db, user, event, str(reminder.id))
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

def reconcile_whatsapp_usage(db: Session, limit: int = 100) -> int:
    """Refresh pending provider-reported message charges; never infer a zero cost."""
    from app.models.entities import MessageUsage
    rows = db.scalars(select(MessageUsage).where(MessageUsage.cost_status == 'pending', MessageUsage.provider_message_id.is_not(None)).order_by(MessageUsage.created_at).with_for_update(skip_locked=True).limit(limit)).all()
    updated = 0
    for row in rows:
        try:
            payload = provider_from_env().message_cost(row.provider_message_id)
            data = payload.get('data', payload)
            cost = data.get('cost') or {}
            amount = cost.get('amount')
            currency = cost.get('currency_code') or cost.get('currency')
            if amount is not None:
                row.cost_amount = amount
                row.currency = currency
                row.cost_status = 'reconciled'
                updated += 1
        except Exception:
            # Leave pending for a later pass; Bird may not have priced an accepted send yet.
            continue
    db.commit()
    return updated

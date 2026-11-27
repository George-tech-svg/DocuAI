"""User-owned important dates and reminder settings."""
from datetime import datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.dependencies import current_user
from app.db.session import get_db
from app.models.entities import Document, DocumentEvent, KnowledgeBase, NotificationPreference, Reminder, User
from app.schemas.events import EventEdit, NotificationPreferencesUpdate, SnoozeRequest

router = APIRouter(tags=['Important dates'])

def _event_view(event: DocumentEvent, document: Document):
    return {'id': event.id, 'document_id': event.document_id, 'document_name': document.original_filename,
        'kind': event.kind, 'title': event.title, 'due_at': event.due_at, 'source_page': event.source_page,
        'source_excerpt': event.source_excerpt, 'confidence': event.confidence, 'status': event.status}

def _owned_event(db: Session, user_id, event_id: UUID):
    event = db.scalar(select(DocumentEvent).where(DocumentEvent.id == event_id, DocumentEvent.user_id == user_id))
    if not event:
        raise HTTPException(404, 'Important date not found.')
    return event

def _ensure_preferences(db: Session, user_id):
    pref = db.get(NotificationPreference, user_id)
    if pref is None:
        pref = NotificationPreference(user_id=user_id)
        db.add(pref)
        db.flush()
    return pref

def _create_reminders(db: Session, event: DocumentEvent, pref: NotificationPreference):
    db.query(Reminder).filter(Reminder.event_id == event.id, Reminder.status == 'scheduled').update({'status': 'cancelled'})
    now = datetime.now(timezone.utc)
    channels = pref.channels or {'in_app': True}
    for days in sorted({int(value) for value in (pref.lead_days or [14, 7, 1]) if 0 <= int(value) <= 365}, reverse=True):
        remind_at = event.due_at - timedelta(days=days)
        if remind_at <= now:
            continue
        for channel in ('in_app', 'email'):
            if channels.get(channel, channel == 'in_app'):
                db.add(Reminder(event_id=event.id, user_id=event.user_id, channel=channel, remind_at=remind_at, status='scheduled'))

@router.get('/documents/{document_id}/events')
def document_events(document_id: UUID, user: User=Depends(current_user), db: Session=Depends(get_db)):
    document = db.scalar(select(Document).join(KnowledgeBase).where(Document.id == document_id, KnowledgeBase.user_id == user.id))
    if not document:
        raise HTTPException(404, 'Document not found.')
    events = db.scalars(select(DocumentEvent).where(DocumentEvent.document_id == document.id).order_by(DocumentEvent.due_at)).all()
    return {'items': [_event_view(event, document) for event in events]}

@router.get('/events/upcoming')
def upcoming_events(user: User=Depends(current_user), db: Session=Depends(get_db)):
    rows = db.execute(select(DocumentEvent, Document).join(Document, Document.id == DocumentEvent.document_id)
        .where(DocumentEvent.user_id == user.id, DocumentEvent.status.in_(['suggested', 'confirmed']))
        .order_by(DocumentEvent.due_at).limit(200)).all()
    return {'items': [_event_view(event, document) for event, document in rows]}

@router.get('/notifications')
def in_app_notifications(user: User=Depends(current_user), db: Session=Depends(get_db)):
    rows = db.execute(select(Reminder, DocumentEvent, Document).join(DocumentEvent, DocumentEvent.id == Reminder.event_id)
        .join(Document, Document.id == DocumentEvent.document_id)
        .where(Reminder.user_id == user.id)
        .order_by(Reminder.remind_at.desc()).limit(100)).all()
    return {'items': [{'id': reminder.id, 'event_id': event.id, 'title': event.title,
        'document_name': document.original_filename, 'channel': reminder.channel, 'remind_at': reminder.remind_at,
        'sent_at': reminder.sent_at, 'status': reminder.status, 'error': reminder.error}
        for reminder, event, document in rows]}

@router.post('/events/{event_id}/confirm')
def confirm_event(event_id: UUID, data: EventEdit, user: User=Depends(current_user), db: Session=Depends(get_db)):
    event = _owned_event(db, user.id, event_id)
    if event.status in {'dismissed', 'done'}:
        raise HTTPException(409, 'This date is no longer available to confirm.')
    event.title, event.kind = data.title.strip(), data.kind
    event.due_at = data.due_at.astimezone(timezone.utc) if data.due_at.tzinfo else data.due_at.replace(tzinfo=timezone.utc)
    event.status = 'confirmed'
    pref = _ensure_preferences(db, user.id)
    _create_reminders(db, event, pref)
    db.commit()
    document = db.get(Document, event.document_id)
    return _event_view(event, document)

@router.post('/events/{event_id}/dismiss', status_code=204)
def dismiss_event(event_id: UUID, user: User=Depends(current_user), db: Session=Depends(get_db)):
    event = _owned_event(db, user.id, event_id)
    event.status = 'dismissed'
    db.query(Reminder).filter(Reminder.event_id == event.id, Reminder.status.in_(['scheduled', 'failed'])).update({'status': 'cancelled'})
    db.commit()

@router.post('/events/{event_id}/done', status_code=204)
def mark_event_done(event_id: UUID, user: User=Depends(current_user), db: Session=Depends(get_db)):
    event = _owned_event(db, user.id, event_id)
    event.status = 'done'
    db.query(Reminder).filter(Reminder.event_id == event.id, Reminder.status.in_(['scheduled', 'failed'])).update({'status': 'cancelled'})
    db.commit()

@router.post('/reminders/{reminder_id}/snooze')
def snooze_reminder(reminder_id: UUID, data: SnoozeRequest, user: User=Depends(current_user), db: Session=Depends(get_db)):
    reminder = db.scalar(select(Reminder).where(Reminder.id == reminder_id, Reminder.user_id == user.id))
    if not reminder or reminder.status not in {'scheduled', 'failed'}:
        raise HTTPException(404, 'Pending reminder not found.')
    remind_at = data.remind_at.astimezone(timezone.utc) if data.remind_at.tzinfo else data.remind_at.replace(tzinfo=timezone.utc)
    if remind_at <= datetime.now(timezone.utc):
        raise HTTPException(422, 'Choose a snooze time in the future.')
    duplicate = db.scalar(select(Reminder.id).where(Reminder.event_id == reminder.event_id, Reminder.channel == reminder.channel, Reminder.remind_at == remind_at, Reminder.id != reminder.id, Reminder.status == 'scheduled').limit(1))
    if duplicate:
        raise HTTPException(409, 'A reminder is already scheduled for that time.')
    reminder.remind_at = remind_at
    reminder.status = 'scheduled'
    reminder.error = None
    reminder.next_attempt_at = None
    db.commit()
    return {'id': reminder.id, 'remind_at': reminder.remind_at, 'status': reminder.status}

@router.post('/events/{event_id}/snooze')
def snooze_event(event_id: UUID, data: SnoozeRequest, user: User=Depends(current_user), db: Session=Depends(get_db)):
    event = _owned_event(db, user.id, event_id)
    if event.status != 'confirmed':
        raise HTTPException(409, 'Confirm this date before snoozing its reminder.')
    reminder = db.scalar(select(Reminder).where(Reminder.event_id == event.id, Reminder.user_id == user.id, Reminder.status.in_(['scheduled', 'failed'])).order_by(Reminder.remind_at).limit(1))
    if not reminder:
        raise HTTPException(404, 'There is no pending reminder to snooze.')
    remind_at = data.remind_at.astimezone(timezone.utc) if data.remind_at.tzinfo else data.remind_at.replace(tzinfo=timezone.utc)
    if remind_at <= datetime.now(timezone.utc):
        raise HTTPException(422, 'Choose a snooze time in the future.')
    duplicate = db.scalar(select(Reminder.id).where(Reminder.event_id == reminder.event_id, Reminder.channel == reminder.channel, Reminder.remind_at == remind_at, Reminder.id != reminder.id, Reminder.status == 'scheduled').limit(1))
    if duplicate:
        raise HTTPException(409, 'A reminder is already scheduled for that time.')
    reminder.remind_at, reminder.status, reminder.error, reminder.next_attempt_at = remind_at, 'scheduled', None, None
    db.commit()
    return {'id': reminder.id, 'remind_at': reminder.remind_at, 'status': reminder.status}

@router.get('/events/{event_id}/ics')
def export_event_ics(event_id: UUID, user: User=Depends(current_user), db: Session=Depends(get_db)):
    event = _owned_event(db, user.id, event_id)
    document = db.get(Document, event.document_id)
    def escape(value: str):
        return value.replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n').replace('\r', '')
    start = event.due_at.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    end = (event.due_at + timedelta(hours=1)).astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    now = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    details = f"{event.source_excerpt}\nPage {event.source_page or 'not available'}\nCheck this date against the original document."
    body = '\r\n'.join(['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//DocuMind AI//Important dates//EN', 'BEGIN:VEVENT', f'UID:{event.id}@documind', f'DTSTAMP:{now}', f'DTSTART:{start}', f'DTEND:{end}', f'SUMMARY:{escape(event.title)}', f'DESCRIPTION:{escape(details)}', f'CATEGORIES:{escape(event.kind)}', 'END:VEVENT', 'END:VCALENDAR', ''])
    filename = (document.original_filename if document else 'event').replace(' ', '-')[:50]
    return Response(body, media_type='text/calendar; charset=utf-8', headers={'Content-Disposition': f'attachment; filename="{filename}-event.ics"'})

@router.get('/notification-preferences')
def get_notification_preferences(user: User=Depends(current_user), db: Session=Depends(get_db)):
    pref = _ensure_preferences(db, user.id)
    db.commit()
    return {'channels': pref.channels, 'lead_days': pref.lead_days, 'quiet_start': pref.quiet_start, 'quiet_end': pref.quiet_end, 'timezone': pref.timezone}

@router.put('/notification-preferences')
def update_notification_preferences(data: NotificationPreferencesUpdate, user: User=Depends(current_user), db: Session=Depends(get_db)):
    if bool(data.quiet_start) != bool(data.quiet_end):
        raise HTTPException(422, 'Set both quiet-hour times or leave both blank.')
    try:
        ZoneInfo(data.timezone)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(422, 'Choose a valid timezone, such as Africa/Nairobi.') from exc
    for value in (data.quiet_start, data.quiet_end):
        if value is not None:
            try:
                datetime.strptime(value, '%H:%M')
            except ValueError as exc:
                raise HTTPException(422, 'Quiet hours must use 24-hour HH:MM time.') from exc
    pref = _ensure_preferences(db, user.id)
    pref.channels = {key: bool(value) for key, value in data.channels.items() if key in {'email', 'in_app'}}
    pref.channels.setdefault('in_app', True)
    pref.lead_days = sorted(set(data.lead_days), reverse=True)
    pref.quiet_start, pref.quiet_end, pref.timezone = data.quiet_start, data.quiet_end, data.timezone
    db.commit()
    return {'channels': pref.channels, 'lead_days': pref.lead_days, 'quiet_start': pref.quiet_start, 'quiet_end': pref.quiet_end, 'timezone': pref.timezone}

"""WhatsApp account linking and fast, signature-verified Bird webhook."""
from datetime import datetime, timedelta, timezone
import hashlib, hmac, json, re, secrets
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.api.dependencies import current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import Job, User, WhatsAppLink, WhatsAppLinkChallenge, WhatsAppMessage, WhatsAppConsentEvent, MessageUsage
from app.services.whatsapp_provider import provider_from_env, verify_standard_webhook
from app.services.whatsapp_policy import command_kind, is_duplicate_message

router = APIRouter(prefix='/channels/whatsapp', tags=['WhatsApp'])

class LinkRequest(BaseModel):
    phone: str = Field(min_length=8, max_length=20)
    consent: bool

class LinkConfirm(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r'^\d{6}$')

def normalize_phone(phone: str) -> str:
    value = re.sub(r'[\s()-]', '', phone)
    if not re.fullmatch(r'\+[1-9]\d{7,14}', value):
        raise HTTPException(422, 'Enter a valid phone number in international format, for example +2547XXXXXXXX.')
    return value

def _code_hash(user_id, phone: str, code: str) -> str:
    return hashlib.sha256(f'{user_id}:{phone}:{code}'.encode()).hexdigest()

@router.get('/link')
def link_status(user: User=Depends(current_user), db: Session=Depends(get_db)):
    link = db.get(WhatsAppLink, user.id)
    return {'linked': bool(link and link.active), 'phone': link.phone_e164 if link and link.active else None,
            'opted_in': bool(link and link.active and link.opted_in_at and not link.opted_out_at)}

@router.post('/link/request')
def request_link(data: LinkRequest, user: User=Depends(current_user), db: Session=Depends(get_db)):
    if not data.consent: raise HTTPException(422, 'Please agree to receive WhatsApp messages before linking your number.')
    phone = normalize_phone(data.phone)
    owner = db.scalar(select(WhatsAppLink.user_id).where(WhatsAppLink.phone_e164 == phone, WhatsAppLink.active.is_(True)))
    if owner and owner != user.id: raise HTTPException(409, 'This WhatsApp number is already linked to another account.')
    since = datetime.now(timezone.utc) - timedelta(days=1)
    attempts = db.scalar(select(func.count()).select_from(WhatsAppLinkChallenge).where(WhatsAppLinkChallenge.user_id == user.id, WhatsAppLinkChallenge.created_at >= since)) or 0
    if attempts >= 5: raise HTTPException(429, 'Too many linking codes requested. Try again tomorrow.')
    now = datetime.now(timezone.utc)
    code = f'{secrets.randbelow(1_000_000):06d}'
    challenge = WhatsAppLinkChallenge(user_id=user.id, phone_e164=phone, code_hash=_code_hash(user.id, phone, code), expires_at=now + timedelta(minutes=10))
    db.add(challenge); db.commit()
    outbound = WhatsAppMessage(user_id=user.id, phone_e164=phone, direction='outbound', kind='template',
        text='WhatsApp account-link verification code sent.', status='sending', idempotency_key=f'whatsapp-link-{challenge.id}')
    db.add(outbound); db.flush()
    usage = MessageUsage(whatsapp_message_id=outbound.id, user_id=user.id, units=1, cost_status='pending')
    db.add(usage); db.commit()
    try:
        slug = get_settings().BIRD_WHATSAPP_OTP_TEMPLATE_SLUG.strip() or 'bird_otp'
        response = provider_from_env().send_template(phone, slug, 'en', {'code': code}, f'whatsapp-link-{challenge.id}')
        payload = response.get('data', response)
        outbound.provider_message_id = str(payload.get('id') or payload.get('whatsapp_id') or '') or None
        outbound.status = 'sent'; usage.provider_message_id = outbound.provider_message_id
        if not outbound.provider_message_id: usage.cost_status = 'unknown'
        db.commit()
    except Exception as exc:
        outbound.status = 'failed'; outbound.error = str(exc)[:500]; usage.cost_status = 'unknown'
        db.delete(challenge); db.commit()
        raise HTTPException(503, str(exc) or 'Could not send a WhatsApp verification code.') from exc
    return {'message': 'A verification code has been sent to WhatsApp. Enter it here or reply LINK followed by the code in WhatsApp. It expires in 10 minutes.'}

def _consume_challenge(db: Session, user_id, phone: str, code: str):
    now = datetime.now(timezone.utc)
    row = db.scalar(select(WhatsAppLinkChallenge).where(WhatsAppLinkChallenge.user_id == user_id, WhatsAppLinkChallenge.phone_e164 == phone, WhatsAppLinkChallenge.consumed_at.is_(None), WhatsAppLinkChallenge.expires_at > now).order_by(WhatsAppLinkChallenge.created_at.desc()).with_for_update().limit(1))
    if not row or row.attempts >= 5: return False
    row.attempts += 1
    if not hmac.compare_digest(row.code_hash, _code_hash(user_id, phone, code)): return False
    row.consumed_at = now
    link = db.get(WhatsAppLink, user_id)
    other = db.scalar(select(WhatsAppLink).where(WhatsAppLink.phone_e164 == phone, WhatsAppLink.active.is_(True), WhatsAppLink.user_id != user_id).with_for_update())
    if other: return False
    if link and link.phone_e164 != phone: link.active = False
    if not link: link = WhatsAppLink(user_id=user_id, phone_e164=phone); db.add(link)
    link.phone_e164, link.active, link.opted_in_at, link.opted_out_at = phone, True, now, None
    link.consent_source = 'web_link_confirmation'
    db.add(WhatsAppConsentEvent(user_id=user_id, phone_e164=phone, action='opt_in', source='web_link_confirmation'))
    return True

@router.post('/link/confirm')
def confirm_link(data: LinkConfirm, user: User=Depends(current_user), db: Session=Depends(get_db)):
    phone = db.scalar(select(WhatsAppLinkChallenge.phone_e164).where(WhatsAppLinkChallenge.user_id == user.id, WhatsAppLinkChallenge.consumed_at.is_(None), WhatsAppLinkChallenge.expires_at > datetime.now(timezone.utc)).order_by(WhatsAppLinkChallenge.created_at.desc()).limit(1))
    if not phone: raise HTTPException(400, 'Request a new WhatsApp verification code first.')
    try:
        if not _consume_challenge(db, user.id, phone, data.code): db.commit(); raise HTTPException(400, 'The code is incorrect or expired. Check it and try again.')
        db.commit()
    except IntegrityError as exc:
        db.rollback(); raise HTTPException(409, 'This WhatsApp number is already linked to another account.') from exc
    return {'linked': True, 'phone': phone, 'opted_in': True}

@router.post('/unlink')
def unlink(user: User=Depends(current_user), db: Session=Depends(get_db)):
    link = db.get(WhatsAppLink, user.id)
    if link and link.active:
        link.active = False
        db.add(WhatsAppConsentEvent(user_id=user.id, phone_e164=link.phone_e164, action='unlink', source='web_settings'))
        db.commit()
    return {'linked': False}

@router.post('/webhook')
async def bird_webhook(request: Request, db: Session=Depends(get_db)):
    settings = get_settings()
    raw = await request.body()
    webhook_id = request.headers.get('webhook-id', '')
    timestamp = request.headers.get('webhook-timestamp', '')
    signature = request.headers.get('webhook-signature', '')
    if not settings.BIRD_WEBHOOK_SECRET: raise HTTPException(503, 'WhatsApp webhook verification is not configured.')
    if not verify_standard_webhook(settings.BIRD_WEBHOOK_SECRET, webhook_id, timestamp, raw, signature): raise HTTPException(401, 'Invalid webhook signature.')
    try: body = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc: raise HTTPException(400, 'Invalid webhook body.') from exc
    event_type = str(body.get('event') or body.get('type') or body.get('event_type') or '')
    data = body.get('payload') or body.get('data') or {}
    workspace_id = str(data.get('workspace_id') or body.get('workspace_id') or '')
    if settings.BIRD_WORKSPACE_ID and workspace_id != settings.BIRD_WORKSPACE_ID:
        raise HTTPException(403, 'Webhook belongs to a different Bird workspace.')
    message_id = str(data.get('whatsapp_id') or data.get('message_id') or data.get('id') or '')
    sender = data.get('from') or data.get('sender') or {}
    phone = sender.get('phone_number') if isinstance(sender, dict) else sender
    if not phone: return {'received': True}
    phone = normalize_phone(str(phone))
    # Persist delivery receipt first. Webhook retries become harmless and never enqueue duplicate work.
    if is_duplicate_message(db, webhook_id, message_id or None, WhatsAppMessage):
        return {'received': True, 'duplicate': True}
    if event_type.lower() not in {'whatsapp.received', 'whatsapp_received', 'message.received'}:
        return {'received': True}
    text_obj = data.get('text')
    text_value = (text_obj.get('body') or text_obj.get('text')) if isinstance(text_obj, dict) else text_obj
    media = data.get('image') or data.get('document') or data.get('media') or {}
    media_id = str(media.get('id')) if isinstance(media, dict) and media.get('id') else None
    mime = media.get('mime_type') if isinstance(media, dict) else None
    safe_payload = {'event_type': event_type}
    if media_id:
        safe_payload['media'] = {'id': media_id, 'mime_type': mime,
            'filename': (media.get('filename') or media.get('file_name')) if isinstance(media, dict) else None}
    link = db.scalar(select(WhatsAppLink).where(WhatsAppLink.phone_e164 == phone, WhatsAppLink.active.is_(True)))
    now = datetime.now(timezone.utc)
    row = WhatsAppMessage(provider_message_id=message_id or None, webhook_id=webhook_id, user_id=link.user_id if link else None,
        phone_e164=phone, direction='inbound', kind='media' if media_id else 'text', text=str(text_value)[:8000] if text_value else None,
        media_id=media_id, media_mime_type=mime, provider_payload=safe_payload, status='queued', idempotency_key=f'inbound:{message_id or webhook_id}')
    db.add(row)
    if link:
        link.last_inbound_at = now
        command = command_kind(str(text_value or ''))
        if command == 'opt_out':
            link.opted_out_at = now
            link.consent_source = 'whatsapp_stop'
            db.add(WhatsAppConsentEvent(user_id=link.user_id, phone_e164=phone, action='opt_out', source='whatsapp_command', provider_message_id=message_id or None))
        elif command == 'opt_in':
            link.opted_in_at, link.opted_out_at = now, None
            link.consent_source = 'whatsapp_start'
            db.add(WhatsAppConsentEvent(user_id=link.user_id, phone_e164=phone, action='opt_in', source='whatsapp_command', provider_message_id=message_id or None))
    elif command_kind(str(text_value or '')) == 'opt_out':
        db.add(WhatsAppConsentEvent(user_id=None, phone_e164=phone, action='opt_out', source='whatsapp_command', provider_message_id=message_id or None))
    try:
        db.flush()
        command = command_kind(str(text_value or ''))
        if link and command not in {'opt_in', 'opt_out'}:
            minute_count = db.scalar(select(func.count()).select_from(WhatsAppMessage).where(
                WhatsAppMessage.user_id == link.user_id, WhatsAppMessage.direction == 'inbound',
                WhatsAppMessage.created_at >= now - timedelta(minutes=1))) or 0
            day_count = db.scalar(select(func.count()).select_from(WhatsAppMessage).where(
                WhatsAppMessage.user_id == link.user_id, WhatsAppMessage.direction == 'inbound',
                WhatsAppMessage.created_at >= now - timedelta(days=1))) or 0
            if minute_count > 10 or day_count > 100:
                row.status = 'rate_limited'
                db.commit()
                return {'received': True, 'rate_limited': True}
        db.add(Job(type='process_whatsapp_message', payload={'message_id': str(row.id)}, max_attempts=5))
        db.commit()
    except IntegrityError:
        db.rollback()
        return {'received': True, 'duplicate': True}
    return {'received': True}

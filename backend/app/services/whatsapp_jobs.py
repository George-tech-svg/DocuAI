"""Durable WhatsApp message handling and cost ledger helpers."""
from datetime import datetime, timedelta, timezone
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import select, func
from app.core.config import get_settings
from app.models.entities import (WhatsAppMessage, WhatsAppLink, WhatsAppLinkChallenge,
    WhatsAppConsentEvent, MessageUsage, KnowledgeBase, User, DocumentEvent, Document,
    LibraryDocument, LibraryChunk, Job)
from app.services.whatsapp_provider import provider_from_env
from app.services.whatsapp_policy import linked_and_opted_in
from app.services.permissions import can

APP_URL = 'https://docuai-jet.vercel.app'

def _send(db, phone: str, text: str, key: str, user_id=None, inbound=None):
    existing = db.scalar(select(WhatsAppMessage).where(WhatsAppMessage.idempotency_key == key).with_for_update())
    if existing and existing.status == 'sent': return existing
    text = text[:1200]
    row = existing or WhatsAppMessage(phone_e164=phone, user_id=user_id, direction='outbound', kind='text', text=text,
        status='sending', related_inbound_message_id=inbound.id if inbound else None, idempotency_key=key)
    row.status, row.text, row.error = 'sending', text, None
    if not existing: db.add(row)
    db.flush()
    usage = db.scalar(select(MessageUsage).where(MessageUsage.whatsapp_message_id == row.id))
    if not usage:
        usage = MessageUsage(whatsapp_message_id=row.id, user_id=user_id, units=1, cost_status='pending')
        db.add(usage)
    db.commit()
    try:
        provider = provider_from_env()
        link = db.get(WhatsAppLink, user_id) if user_id else None
        in_window = bool(inbound or (link and link.last_inbound_at and datetime.now(timezone.utc) - link.last_inbound_at <= timedelta(hours=24)))
        if in_window:
            result = provider.send_text(phone, text, key)
        else:
            slug = get_settings().BIRD_WHATSAPP_NOTIFICATION_TEMPLATE_SLUG.strip()
            if not slug:
                raise RuntimeError('This WhatsApp message is outside the 24-hour service window. Configure an approved notification template before sending it.')
            result = provider.send_template(phone, slug, 'en', {'message': text[:900]}, key)
        payload = result.get('data', result)
        row.provider_message_id = str(payload.get('id') or payload.get('whatsapp_id') or '') or None
        row.status = 'sent'; row.provider_payload = result
        usage.provider_message_id = row.provider_message_id
        if not row.provider_message_id: usage.cost_status = 'unknown'
        db.commit()
        return row
    except Exception as exc:
        row.status = 'failed'; row.error = str(exc)[:500]; usage.cost_status = 'unknown'; db.commit()
        raise

def _link_code(db, phone, code, inbound):
    now = datetime.now(timezone.utc)
    rows = db.scalars(select(WhatsAppLinkChallenge).where(WhatsAppLinkChallenge.phone_e164 == phone,
        WhatsAppLinkChallenge.consumed_at.is_(None), WhatsAppLinkChallenge.expires_at > now,
        WhatsAppLinkChallenge.attempts < 5).order_by(WhatsAppLinkChallenge.created_at.desc()).limit(5).with_for_update()).all()
    import hashlib, hmac
    for challenge in rows:
        expected = hashlib.sha256(f'{challenge.user_id}:{phone}:{code}'.encode()).hexdigest()
        challenge.attempts += 1
        if not hmac.compare_digest(challenge.code_hash, expected): continue
        link = db.scalar(select(WhatsAppLink).where(WhatsAppLink.phone_e164 == phone, WhatsAppLink.active.is_(True)).with_for_update())
        if link and link.user_id != challenge.user_id:
            challenge.consumed_at = now
            db.commit(); return False
        old = db.get(WhatsAppLink, challenge.user_id)
        if old and old.phone_e164 != phone: old.active = False
        if not old:
            old = WhatsAppLink(user_id=challenge.user_id, phone_e164=phone); db.add(old)
        old.phone_e164, old.active, old.opted_in_at, old.opted_out_at = phone, True, now, None
        old.consent_source = 'whatsapp_link_code'
        challenge.consumed_at = now
        db.add(WhatsAppConsentEvent(user_id=challenge.user_id, phone_e164=phone, action='opt_in', source='whatsapp_link_code', provider_message_id=inbound.provider_message_id))
        inbound.user_id = challenge.user_id
        db.commit(); return True
    db.commit()
    return False

def process_whatsapp_message(db, message_id: UUID):
    inbound = db.get(WhatsAppMessage, message_id)
    if not inbound or inbound.direction != 'inbound': return
    text = (inbound.text or '').strip()
    lower = text.lower()
    key = f'wa-reply-{inbound.id}'
    link = db.scalar(select(WhatsAppLink).where(WhatsAppLink.phone_e164 == inbound.phone_e164, WhatsAppLink.active.is_(True)))
    if not link:
        match = text.split(maxsplit=1)
        if len(match) == 2 and match[0].lower() == 'link' and match[1].isdigit() and _link_code(db, inbound.phone_e164, match[1], inbound):
            _send(db, inbound.phone_e164, 'Your WhatsApp is linked to DocuMind. Send help to see what you can do.', key, inbound.user_id, inbound); return
        _send(db, inbound.phone_e164, 'This number is not linked to a DocuMind account. Sign up at the DocuMind app, then link WhatsApp in Settings.', key, None, inbound); return
    user = db.get(User, link.user_id)
    if not user or not user.is_active:
        _send(db, inbound.phone_e164, 'This DocuMind account is unavailable. Please contact support.', key, link.user_id, inbound); return
    # Webhook already records STOP/START before acknowledgement; do not answer content while opted out.
    if lower in {'stop','unsubscribe','quit'}:
        _send(db, inbound.phone_e164, 'You are opted out of DocuMind WhatsApp messages. Send START if you want to opt in again.', key, user.id, inbound); return
    if not linked_and_opted_in(link):
        if lower in {'start','unstop','subscribe'}:
            _send(db, inbound.phone_e164, 'You are opted in. You can send questions after choosing a folder in DocuMind.', key, user.id, inbound)
        else:
            inbound.status = 'opted_out'
            db.commit()
        return
    since = datetime.now(timezone.utc) - timedelta(minutes=1)
    per_minute = db.scalar(select(func.count()).select_from(WhatsAppMessage).where(WhatsAppMessage.user_id == user.id, WhatsAppMessage.direction == 'inbound', WhatsAppMessage.created_at >= since)) or 0
    since_day = datetime.now(timezone.utc) - timedelta(days=1)
    per_day = db.scalar(select(func.count()).select_from(WhatsAppMessage).where(WhatsAppMessage.user_id == user.id, WhatsAppMessage.direction == 'inbound', WhatsAppMessage.created_at >= since_day)) or 0
    if per_minute > 10 or per_day > 100:
        inbound.status = 'rate_limited'; db.commit(); return
    if inbound.kind == 'media' or lower not in {'help','hi','hello','folders','library','upcoming','more','stop','unsubscribe','quit','start','unstop','subscribe'} and not lower.startswith('use '):
        try:
            from app.api.dependencies import subscribed_user
            subscribed_user(user, db)
        except HTTPException as exc:
            detail = getattr(exc, 'detail', None)
            _send(db, inbound.phone_e164, detail or f'Choose a plan in DocuMind before using chat and uploads: {APP_URL}', key, user.id, inbound)
            return
    if lower in {'help','hi','hello'}:
        result = 'Send a question about your selected folder, or use folders, use <folder name>, library, upcoming, or stop. Send MORE for the previous full answer in smaller parts.'
    elif lower in {'start','unstop','subscribe'}:
        result = 'You are opted in to DocuMind WhatsApp. Choose a folder in the web app, then ask a question here.'
    elif lower == 'folders':
        folders = db.scalars(select(KnowledgeBase).where(KnowledgeBase.is_active.is_(True))).all()
        names = [kb.name for kb in folders if can(user, 'chat', kb, db)]
        result = 'Your available folders: ' + (', '.join(names[:25]) if names else 'none yet. Create one in the DocuMind web app.')
    elif lower.startswith('use '):
        name = text[4:].strip()
        folders = db.scalars(select(KnowledgeBase).where(KnowledgeBase.is_active.is_(True))).all()
        match = next((kb for kb in folders if can(user, 'chat', kb, db) and kb.name.lower() == name.lower()), None)
        if match:
            link.last_used_knowledge_base_id = match.id; link.last_scope_type = 'folder'; db.commit()
            result = f'Now asking questions across {match.name}. Send your question.'
        else: result = 'I could not find that folder. Send folders to see names you can use.'
    elif lower == 'library':
        link.last_scope_type = 'library'; db.commit()
        result = 'Library mode is selected. Ask about documents in the shared library. Answers use retrieved sources only.'
    elif lower == 'upcoming':
        candidates = db.execute(select(DocumentEvent, Document).join(Document, Document.id == DocumentEvent.document_id).where(DocumentEvent.status == 'confirmed', DocumentEvent.due_at >= datetime.now(timezone.utc)).order_by(DocumentEvent.due_at).limit(200)).all()
        rows = [(event, document) for event, document in candidates if can(user, 'read', event, db)][:5]
        result = 'Upcoming dates: ' + ('; '.join(f'{e.title}: {e.due_at:%d %b %Y} ({d.original_filename}, page {e.source_page or "?"})' for e,d in rows) if rows else 'No confirmed upcoming dates were found.')
    elif lower == 'more':
        last = db.scalar(select(WhatsAppMessage).where(WhatsAppMessage.user_id == user.id, WhatsAppMessage.direction == 'inbound', WhatsAppMessage.response_text.is_not(None)).order_by(WhatsAppMessage.created_at.desc()).limit(1))
        if last and last.response_offset < len(last.response_text):
            start = last.response_offset
            result = last.response_text[start:start + 1000]
            last.response_offset = start + len(result)
            result += f'\n\nSend MORE for the next part. Full answer: {APP_URL}' if last.response_offset < len(last.response_text) else f'\n\nThat is the rest. Full workspace: {APP_URL}'
            db.commit()
        else:
            result = f'There is no more text in the previous answer. Open {APP_URL} for your workspace.'
    elif inbound.kind == 'media':
        _receive_document(db, user, link, inbound)
        return
    else:
        try:
            result = _answer_from_scope(db, user, link, inbound, text)
        except Exception:
            import logging
            logging.getLogger('documind.whatsapp').exception('WhatsApp question could not be answered.')
            result = 'I could not process that question right now. Please try again, or open your workspace: ' + APP_URL
    if lower != 'more' and not inbound.response_text:
        inbound.response_text = result
    if lower != 'more' and inbound.response_text:
        inbound.response_offset = len(result)
    _send(db, inbound.phone_e164, result, key, user.id, inbound)

def _receive_document(db, user, link, inbound):
    from app.core.config import max_upload_mb
    from app.services.file_validation import validate_upload
    from app.services.storage import store_file
    from app.models.entities import Document, WhatsAppDocumentUpload
    kb = db.get(KnowledgeBase, link.last_used_knowledge_base_id) if link.last_used_knowledge_base_id else None
    if not kb or not can(user, 'upload', kb, db):
        _send(db, inbound.phone_e164, f'Choose a folder where you can upload in the DocuMind app, then send the file again. {APP_URL}', f'wa-reply-{inbound.id}', user.id, inbound); return
    mime = (inbound.media_mime_type or '').split(';')[0].lower()
    suffix_by_mime = {'application/pdf': '.pdf', 'text/plain': '.txt', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx', 'image/jpeg': '.jpg', 'image/png': '.png', 'image/heic': '.heic'}
    suffix = suffix_by_mime.get(mime)
    if not suffix:
        _send(db, inbound.phone_e164, 'I could not use this attachment. Send a PDF, TXT, DOCX, JPG, PNG, or HEIC file (10 MB maximum).', f'wa-reply-{inbound.id}', user.id, inbound); return
    try:
        raw = inbound.provider_payload.get('payload') or inbound.provider_payload.get('data') or inbound.provider_payload
        media = raw.get('image') or raw.get('document') or raw.get('media') or {}
        provider_message_id = inbound.provider_message_id
        if not provider_message_id:
            raise RuntimeError('The WhatsApp message ID is missing.')
        content, received_mime = provider_from_env().fetch_media(provider_message_id, inbound.media_id, max_upload_mb() * 1_000_000)
        filename = (media.get('filename') or media.get('file_name') or f'whatsapp-upload{suffix}') if isinstance(media, dict) else f'whatsapp-upload{suffix}'
        filename, content_type = validate_upload(filename, content, max_upload_mb())
        stored = store_file(filename, content)
        document = Document(knowledge_base_id=kb.id, uploaded_by_user_id=user.id, original_filename=filename,
            content_type=content_type, file_size_bytes=len(content), cloudinary_public_id=stored['public_id'],
            cloudinary_resource_type=stored['resource_type'], storage_url=stored['url'], status='pending', progress_stage='uploading')
        db.add(document); db.flush()
        db.add(WhatsAppDocumentUpload(document_id=document.id, inbound_message_id=inbound.id, user_id=user.id))
        db.add(Job(type='index_document', payload={'document_id': str(document.id)}, max_attempts=4))
        db.commit()
        _send(db, inbound.phone_e164, 'Received. I will tell you when it is ready.', f'wa-reply-{inbound.id}', user.id, inbound)
    except Exception as exc:
        db.rollback()
        safe = str(exc)[:300] if isinstance(exc, (ValueError, RuntimeError)) else 'The file could not be processed.'
        _send(db, inbound.phone_e164, f'Could not process this attachment: {safe} Please try again or upload it in the DocuMind app.', f'wa-reply-{inbound.id}', user.id, inbound)

def _answer_from_scope(db, user, link, inbound, question):
    from app.services.embeddings import embed_texts
    from app.services.retrieval import retrieve
    import asyncio
    from app.services.language import detect_language, requested_language, requested_translation_language, translate_search_query_to_english
    from app.services.trusted_answers import trusted_answer
    from app.services.answer_validation import confidence_from_retrieval
    language = requested_language(question, getattr(user, 'answer_language', 'auto') or 'auto')
    translation_target = requested_translation_language(question)
    search_query = asyncio.run(translate_search_query_to_english(question)) if detect_language(question) in {'sw', 'mixed'} else question
    if link.last_scope_type == 'library':
        from app.models.entities import LibraryChunk
        query_vector = embed_texts([search_query])[0]
        hits = db.execute(select(LibraryChunk, LibraryDocument).join(LibraryDocument, LibraryDocument.id == LibraryChunk.library_document_id)
            .where(LibraryDocument.status == 'ready', LibraryDocument.is_current.is_(True))
            .order_by(LibraryChunk.embedding.cosine_distance(query_vector)).limit(5)).all()
        if not hits:
            return f'The shared library has no ready sources for this question. Check the official source or ask in the DocuMind app: {APP_URL}'
        context = '\n\n'.join(f'[{i}] {doc.title}, {doc.version_label or "version not listed"}, page {chunk.page_number or "?"}: {chunk.content}' for i,(chunk,doc) in enumerate(hits,1))
        passage_texts = [chunk.content for chunk, _doc in hits]
        response, _valid = asyncio.run(trusted_answer(question, context, passage_texts, language=language,
            library_mode=True, translation_target=translation_target, whatsapp_mode=True))
        refs = '; '.join(f'[{i}] {doc.title} ({doc.version_label or "version not listed"}) p.{chunk.page_number or "?"}' for i,(chunk,doc) in enumerate(hits,1))
        score, confidence = confidence_from_retrieval(1 / 61, 0)
        full = f'{response}\nSource match: {confidence}\nSources: {refs}\nSend MORE for the full answer: {APP_URL}'
        inbound.response_text = full
        return f'{response[:540]}\nSource match: {confidence}\nSources: {refs[:300]}\nSend MORE: {APP_URL}'[:1200]
    kb = db.get(KnowledgeBase, link.last_used_knowledge_base_id) if link.last_used_knowledge_base_id else None
    if not kb or not can(user, 'chat', kb, db):
        return f'Choose a folder in the DocuMind app first. In WhatsApp, send folders and then use <folder name>. {APP_URL}'
    vector = embed_texts([search_query])[0]
    hits, meta = retrieve(db, kb.id, search_query, limit=5, query_vector=vector)
    passages = [{'content': hit[0].content, 'document_name': hit[1], 'page_number': hit[0].page_number} for hit in hits]
    if not passages: return 'I could not find relevant text in this folder. Check that it contains ready documents, or ask in the web app.'
    context = '\n\n'.join(f'[{i}] {p.get("document_name", "Document")}, page {p.get("page_number") or "unknown"}: {p["content"]}' for i,p in enumerate(passages, 1))
    response, _valid = asyncio.run(trusted_answer(question, context, [p['content'] for p in passages],
        language=language, translation_target=translation_target, whatsapp_mode=True))
    sources = '; '.join(f'[{i}] {p.get("document_name", "Document")} p.{p.get("page_number") or "?"}' for i,p in enumerate(passages, 1))
    score, confidence = confidence_from_retrieval(meta.get('top_fusion_score', 0), meta.get('agreeing_passages', 0))
    full = f'{response}\n\nSource match: {confidence}\nSources: {sources}\n\nSend MORE for the full answer in DocuMind: {APP_URL}'
    inbound.response_text = full
    return f'{response[:650]}\nSource match: {confidence}\nSources: {sources[:300]}\nSend MORE: {APP_URL}'[:1200]

def notify_document_ready(db, document_id: UUID):
    from app.models.entities import WhatsAppDocumentUpload, DocumentChunk
    from sqlalchemy import select
    upload = db.scalar(select(WhatsAppDocumentUpload).where(WhatsAppDocumentUpload.document_id == document_id))
    if not upload or upload.notified_at: return
    document = db.get(Document, document_id)
    link = db.get(WhatsAppLink, upload.user_id)
    if not document or not link or not link.active or not link.opted_in_at or link.opted_out_at: return
    chunks = db.scalars(select(DocumentChunk).where(DocumentChunk.document_id == document.id).order_by(DocumentChunk.chunk_index).limit(4)).all()
    context = '\n'.join(chunk.content[:1800] for chunk in chunks)
    summary = 'The document is ready. You can now ask questions about it.'
    if context:
        try:
            import asyncio
            from app.services.llm import answer_question
            summary = asyncio.run(answer_question('Give a short, simple summary of this document. Use the language most common in the source text.', context, whatsapp_mode=True))
        except Exception:
            summary = 'The document is ready. I could not make a summary right now, but you can ask questions about it.'
    dates = db.scalars(select(DocumentEvent).where(DocumentEvent.document_id == document.id, DocumentEvent.status.in_(['suggested','confirmed'])).order_by(DocumentEvent.due_at).limit(5)).all()
    date_text = '\nImportant dates to check: ' + '; '.join(f'{event.title} — {event.due_at:%d %b %Y}, page {event.source_page or "?"}' for event in dates) if dates else ''
    body = f'{document.original_filename} is ready.\n{summary}{date_text}\nAsk about it in DocuMind: {APP_URL}'
    _send(db, link.phone_e164, body, f'wa-document-ready-{document.id}', upload.user_id)
    upload.notified_at = datetime.now(timezone.utc)
    db.commit()

def notify_document_failed(db, document_id: UUID):
    from app.models.entities import WhatsAppDocumentUpload
    upload = db.scalar(select(WhatsAppDocumentUpload).where(WhatsAppDocumentUpload.document_id == document_id))
    if not upload or upload.notified_at: return
    link = db.get(WhatsAppLink, upload.user_id)
    if not linked_and_opted_in(link): return
    document = db.get(Document, document_id)
    reason = document.processing_error if document else None
    body = f'We could not process {document.original_filename if document else "your file"}. {reason or "Please try another file or upload it again in DocuMind."} {APP_URL}'
    _send(db, link.phone_e164, body, f'wa-document-failed-{document_id}', upload.user_id)
    upload.notified_at = datetime.now(timezone.utc)
    db.commit()

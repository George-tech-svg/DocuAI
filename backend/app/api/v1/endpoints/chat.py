"""Chat with indexed documents and save conversation history."""

import json
import logging
from time import perf_counter
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from app.db.session import get_db, get_engine
from app.api.dependencies import current_user, subscribed_user
from app.models.user import User
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.document import Document
from app.schemas.chat import ChatRequest, ChatResponse, Source, ConversationResponse, MessageResponse
from app.services.document_service import owned_kb, owned_document
from app.services.retrieval import retrieve
from app.services.embeddings import embed_texts
from app.services.llm import rewrite_follow_up_question
from app.core.config import get_settings
from app.services.language import detect_language, requested_language, requested_translation_language, translate_search_query_to_english
from app.services.answer_validation import confidence_from_retrieval, FALLBACK_ANSWER
from app.services.trusted_answers import trusted_answer
from app.services.permissions import can
from app.models.entities import AuditEvent, LibraryCollection, LibraryDocument, LibraryChunk, KnowledgeBase, OrganizationMember, AnswerFeedback
from app.services.security_controls import enforce_rate_limit
from app.services.user_guide import GUIDE_CONTEXT, GUIDE_PASSAGES, is_guide_question
from sqlalchemy import literal_column
router = APIRouter(tags=['Chat'])
logger = logging.getLogger(__name__)

class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    is_archived: bool | None = None
    is_pinned: bool | None = None
    visibility: str | None = Field(default=None, pattern='^(private|shared)$')

class AnswerFeedbackRequest(BaseModel):
    rating: str = Field(pattern='^(up|down|report)$')
    comment: str | None = Field(default=None, max_length=2000)

def _resolve_scope(db, user_id, data: ChatRequest):
    library_collection_id = data.library_collection_id
    if data.scope_type == 'library':
        knowledge_base_id = None
        document_id = None
        if data.scope_id is not None:
            library_collection_id = data.scope_id
        if library_collection_id and not db.get(LibraryCollection, library_collection_id):
            raise HTTPException(404, 'Library collection not found')
    elif data.scope_type == 'folder_library':
        knowledge_base_id = data.scope_id
        document_id = None
        if not knowledge_base_id: raise HTTPException(400, 'Choose a folder before combining it with the library.')
        owned_kb(db, user_id, knowledge_base_id, 'chat')
        if library_collection_id and not db.get(LibraryCollection, library_collection_id):
            raise HTTPException(404, 'Library collection not found')
    elif data.scope_type == 'folder':
        knowledge_base_id = data.scope_id
        document_id = None
        if not knowledge_base_id: raise HTTPException(400, 'Choose a folder before starting a folder chat.')
        owned_kb(db, user_id, knowledge_base_id, 'chat')
    else:
        if not data.scope_id: raise HTTPException(400, 'Choose a document before starting a document chat.')
        document = db.scalar(select(Document).where(Document.id == data.scope_id))
        if document is None:
            raise HTTPException(404, 'Document not found')
        knowledge_base_id = document.knowledge_base_id
        document_id = document.id
        owned_document(db, user_id, knowledge_base_id, document_id, 'chat')
    conversation = None
    if data.conversation_id:
        conversation = db.scalar(select(Conversation).where(
            Conversation.id == data.conversation_id,
            Conversation.knowledge_base_id == knowledge_base_id,
            Conversation.document_id == document_id,
            Conversation.scope_type == data.scope_type,
            Conversation.library_collection_id == library_collection_id,
        ))
        user = db.get(User, user_id)
        if conversation is None or not can(user, 'chat', conversation, db):
            raise HTTPException(404, 'Conversation not found')
    if data.scope_type == 'folder' and db.scalar(select(Document.id).where(
        Document.knowledge_base_id == knowledge_base_id,
        Document.status == 'ready',
    ).limit(1)) is None:
        raise HTTPException(400, 'This folder has no ready documents yet. Upload a PDF, TXT, DOCX, JPG, PNG, or HEIC file and wait until it is ready before chatting.')
    if data.scope_type in ('library', 'folder_library') and db.scalar(select(LibraryDocument.id).where(
        LibraryDocument.status == 'ready', LibraryDocument.is_current.is_(True),
        *([LibraryDocument.collection_id == library_collection_id] if library_collection_id else []),
    ).limit(1)) is None and data.scope_type == 'library':
        raise HTTPException(400, 'The selected library has no ready documents yet.')
    return knowledge_base_id, document_id, conversation, library_collection_id

def _load_follow_up_context(user_id, data: ChatRequest):
    """Validate the requested scope and load recent turns before query rewriting."""
    with sessionmaker(bind=get_engine())() as db:
        _, _, conversation, _ = _resolve_scope(db, user_id, data)
        if conversation is None:
            return []
        recent = db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.message_index.desc(), Message.created_at.desc())
            .limit(8)
        ).all()
        return [{'role': item.role, 'content': item.content} for item in reversed(recent)]


def _prepare_guide_chat(user_id, data: ChatRequest):
    """Validate the selected chat location before answering from the guide."""
    with sessionmaker(bind=get_engine())() as db:
        knowledge_base_id, document_id, conversation, library_collection_id = _resolve_scope(db, user_id, data)
        return knowledge_base_id, document_id, conversation.id if conversation else None, library_collection_id


async def _answer_guide_chat(user: User, data: ChatRequest, language: str, translation_target: str | None):
    knowledge_base_id, document_id, conversation_id, library_collection_id = await run_in_threadpool(
        _prepare_guide_chat, user.id, data
    )
    answer, supported = await trusted_answer(
        data.question, GUIDE_CONTEXT, GUIDE_PASSAGES, language=language,
        strict_grounding=True, translation_target=translation_target,
    )
    source = Source(filename="DocuMind user guide", excerpt="Step-by-step help for files, folders, teams, public documents, chats, tools, and privacy.")
    confidence_score = 1.0 if supported else 0.0
    answer_metadata = {
        'answer_language': language,
        'confidence_score': confidence_score,
        'confidence_label': 'Strong match' if supported else 'Weak match',
        'search_query': 'DocuMind user guide',
        'model_version': get_settings().DEEPSEEK_MODEL,
    }
    saved_conversation_id, assistant_message_id = await run_in_threadpool(
        _save_chat, user.id, knowledge_base_id, document_id, library_collection_id,
        data.scope_type, data.visibility, conversation_id, data.question,
        'DocuMind user guide', answer, [source], answer_metadata,
    )
    return ChatResponse(
        answer=answer, conversation_id=saved_conversation_id,
        assistant_message_id=assistant_message_id, sources=[source],
        answer_language=language, confidence_score=confidence_score,
        confidence_label=answer_metadata['confidence_label'], search_query='DocuMind user guide',
    )

def _prepare_chat(user_id, data: ChatRequest, search_query, query_vector):
    """Run chat authorization and retrieval in one worker-owned DB session."""
    with sessionmaker(bind=get_engine())() as db:
        knowledge_base_id, document_id, conversation, library_collection_id = _resolve_scope(db, user_id, data)
        ranked = []
        path_parts = []
        vector_count = keyword_count = 0
        retrieval_scores = []
        agreeing_passages = 0
        evidence_passages = []
        if knowledge_base_id:
            private_hits, private_details = retrieve(db, knowledge_base_id, search_query, query_vector=query_vector, document_id=document_id, limit=5)
            ranked.extend((rank, 'document', hit) for rank, hit in enumerate(private_hits, 1))
            path_parts.append(private_details['path'])
            vector_count += private_details['vector_top_five']; keyword_count += private_details['keyword_top_five']
            retrieval_scores.append(private_details.get('top_fusion_score', 0.0))
            agreeing_passages += private_details.get('agreeing_passages', 0)
        if data.scope_type in ('library', 'folder_library'):
            text_query = func.websearch_to_tsquery(literal_column("'simple'"), search_query)
            base = select(LibraryChunk, LibraryDocument, LibraryCollection.name.label('collection_name')).join(LibraryDocument).join(LibraryCollection).where(LibraryDocument.status == 'ready', LibraryDocument.is_current.is_(True))
            if library_collection_id: base = base.where(LibraryDocument.collection_id == library_collection_id)
            vector_hits = db.execute(base.order_by(LibraryChunk.embedding.cosine_distance(query_vector)).limit(20)).all()
            tsv = func.to_tsvector(literal_column("'simple'"), LibraryChunk.content)
            keyword_hits = db.execute(base.where(tsv.op('@@')(text_query)).order_by(func.ts_rank_cd(tsv, text_query).desc()).limit(20)).all()
            fused = {}
            for rank, hit in enumerate(vector_hits, 1):
                entry = fused.setdefault(hit[0].id, {'hit': hit, 'score': 0.0, 'vector': False, 'keyword': False})
                entry['score'] += 1 / (60 + rank); entry['vector'] = True
            for rank, hit in enumerate(keyword_hits, 1):
                entry = fused.setdefault(hit[0].id, {'hit': hit, 'score': 0.0, 'vector': False, 'keyword': False})
                entry['score'] += 1 / (60 + rank); entry['keyword'] = True
            ordered_library = sorted(fused.values(), key=lambda entry: entry['score'], reverse=True)[:5]
            library_hits = [entry['hit'] for entry in ordered_library]
            ranked.extend((rank, 'library', hit) for rank, hit in enumerate(library_hits, 1))
            path_parts.append('hybrid' if keyword_hits else 'vector-only')
            vector_count += sum(entry['vector'] for entry in ordered_library); keyword_count += sum(entry['keyword'] for entry in ordered_library)
            if ordered_library:
                retrieval_scores.append(ordered_library[0]['score'])
                agreeing_passages += sum(entry['vector'] and entry['keyword'] for entry in ordered_library)
        combined = {}
        for rank, kind, hit in ranked:
            chunk = hit[0]
            entry = combined.setdefault((kind, chunk.id), {'kind': kind, 'hit': hit, 'score': 0.0})
            entry['score'] += 1 / (60 + rank)
        ordered = sorted(combined.values(), key=lambda entry: entry['score'], reverse=True)[:5]
        sources, context_parts = [], []
        for i, entry in enumerate(ordered, 1):
            kind, hit = entry['kind'], entry['hit']; chunk = hit[0]
            if kind == 'library':
                doc, collection_name = hit[1], hit[2]
                name = f'{doc.title} — {doc.version_label}'
                sources.append(Source(filename=name, page_number=chunk.page_number, excerpt=chunk.content[:300], source_type='library', version_label=doc.version_label, section_title=chunk.section_title, source_url=doc.source_url))
                label = f'{name}, {chunk.section_title or "section not identified"}, page {chunk.page_number or "not identified"} ({collection_name})'
            else:
                _, name, doc_id = hit
                sources.append(Source(document_id=doc_id, filename=name, page_number=chunk.page_number, excerpt=chunk.content[:300]))
                label = f'{name}, page {chunk.page_number or "not identified"}'
            context_parts.append(f'[{i}] {label}: {chunk.content}')
            evidence_passages.append(chunk.content)
        has_processing_documents = bool(knowledge_base_id and db.scalar(select(Document.id).where(Document.knowledge_base_id == knowledge_base_id, Document.status.in_(['pending', 'processing'])).limit(1)))
        top_score = max(retrieval_scores, default=0.0)
        confidence_score, confidence_label = confidence_from_retrieval(top_score, agreeing_passages)
        detail = {'path': '+'.join(path_parts) or 'library-only', 'vector_top_five': vector_count, 'keyword_top_five': keyword_count,
                  'top_fusion_score': top_score, 'agreeing_passages': agreeing_passages,
                  'confidence_score': confidence_score, 'confidence_label': confidence_label}
        return conversation.id if conversation else None, knowledge_base_id, document_id, library_collection_id, sources, '\n\n'.join(context_parts), evidence_passages, bool(ordered), has_processing_documents, detail

def _save_chat(user_id, knowledge_base_id, document_id, library_collection_id, scope_type, visibility, conversation_id, question, search_query, answer, sources, answer_metadata):
    """Persist the completed exchange in a session owned by this worker."""
    with sessionmaker(bind=get_engine())() as db:
        if conversation_id:
            conversation = db.scalar(select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.knowledge_base_id == knowledge_base_id,
                Conversation.document_id == document_id,
                Conversation.scope_type == scope_type,
                Conversation.library_collection_id == library_collection_id,
            ).with_for_update())
            user = db.get(User, user_id)
            if conversation is None or not can(user, 'chat', conversation, db):
                raise HTTPException(404, 'Conversation not found')
        else:
            kb = db.get(KnowledgeBase, knowledge_base_id) if knowledge_base_id else None
            resolved_visibility = visibility if kb and kb.organization_id and visibility == 'shared' else 'private'
            conversation = Conversation(
                user_id=user_id,
                knowledge_base_id=knowledge_base_id,
                document_id=document_id,
                library_collection_id=library_collection_id,
                visibility=resolved_visibility,
                scope_type=scope_type,
                title=question[:100],
                is_archived=False,
            )
            db.add(conversation)
            db.flush()
        next_message_index = db.scalar(
            select(func.coalesce(func.max(Message.message_index), -1)).where(
                Message.conversation_id == conversation.id
            )
        ) + 1
        db.add(Message(
            conversation_id=conversation.id,
            message_index=next_message_index,
            role='user',
            actor_user_id=user_id,
            content=question,
            metadata_json=json.dumps({'search_query': search_query}),
        ))
        assistant_message = Message(
            conversation_id=conversation.id,
            message_index=next_message_index + 1,
            role='assistant',
            actor_user_id=user_id,
            content=answer,
            sources_json=json.dumps([s.model_dump(mode='json') for s in sources]),
            metadata_json=json.dumps(answer_metadata),
            model_name=answer_metadata.get('model_version'),
        )
        db.add(assistant_message)
        db.flush()
        db.commit()
        return conversation.id, assistant_message.id

@router.post('/chat', response_model=ChatResponse)
async def chat(data: ChatRequest, user: User=Depends(current_user), db: Session=Depends(get_db)):
    # Shared public-reference questions are available to every signed-in user;
    # private documents and combined folder chats still require an active plan.
    if data.scope_type != 'library':
        subscribed_user(user, db)
    enforce_rate_limit(db, 'chat-user', str(user.id), 40, 60)
    started = perf_counter()
    try:
        if is_guide_question(data.question):
            language = requested_language(data.question, user.answer_language or 'auto')
            return await _answer_guide_chat(
                user, data, language, requested_translation_language(data.question)
            )
        stage_started = perf_counter()
        recent_messages = await run_in_threadpool(_load_follow_up_context, user.id, data)
        search_query = await rewrite_follow_up_question(data.question, recent_messages)
        language = requested_language(data.question, user.answer_language or 'auto')
        translation_target = requested_translation_language(data.question)
        if detect_language(search_query) in {'sw', 'mixed'}:
            search_query = await translate_search_query_to_english(search_query)
        logger.warning('Follow-up query preparation completed in %.1f seconds (%s prior message(s)).', perf_counter() - stage_started, len(recent_messages))
        stage_started = perf_counter()
        query_vector = (await run_in_threadpool(embed_texts, [search_query]))[0]
        logger.warning('Chat query embedding completed in %.1f seconds.', perf_counter() - stage_started)
        stage_started = perf_counter()
        conversation_id, knowledge_base_id, document_id, library_collection_id, sources, context, evidence_passages, has_hits, has_processing_documents, retrieval_details = await run_in_threadpool(
            _prepare_chat, user.id, data, search_query, query_vector
        )
        logger.warning(
            'Chat retrieval completed in %.1f seconds (%s source(s)); path=%s, top-five contributions vector=%s keyword=%s.',
            perf_counter() - stage_started, len(sources), retrieval_details['path'],
            retrieval_details['vector_top_five'], retrieval_details['keyword_top_five'],
        )
        stage_started = perf_counter()
        if has_hits:
            answer, _valid = await trusted_answer(data.question, context, evidence_passages, language=language,
                library_mode=data.scope_type in ('library', 'folder_library'),
                strict_grounding=retrieval_details['confidence_label'] == 'Weak match',
                translation_target=translation_target)
        elif has_processing_documents:
            answer = 'Your document is still being processed and is not searchable yet. Please wait until its status changes to ready, then ask again.'
        else:
            answer = FALLBACK_ANSWER
            if data.scope_type in ('library', 'folder_library'):
                answer += '\n\n*General information only, not legal or tax advice. Check the official source.*'
        logger.warning('Chat answer generation completed in %.1f seconds.', perf_counter() - stage_started)
        stage_started = perf_counter()
        answer_metadata = {'answer_language': language, 'confidence_score': retrieval_details['confidence_score'],
            'confidence_label': retrieval_details['confidence_label'], 'search_query': search_query,
            'model_version': get_settings().DEEPSEEK_MODEL}
        saved_conversation_id, assistant_message_id = await run_in_threadpool(
            _save_chat, user.id, knowledge_base_id, document_id, library_collection_id, data.scope_type, data.visibility, conversation_id,
            data.question, search_query, answer, sources, answer_metadata,
        )
        logger.warning('Chat persistence completed in %.1f seconds; total %.1f seconds.', perf_counter() - stage_started, perf_counter() - started)
        return ChatResponse(answer=answer, conversation_id=saved_conversation_id, assistant_message_id=assistant_message_id,
            sources=sources, answer_language=language, confidence_score=retrieval_details['confidence_score'],
            confidence_label=retrieval_details['confidence_label'], search_query=search_query)
    except Exception:
        logger.exception('Chat request failed for user %s and scope %s after %.1f seconds.', user.id, data.scope_id, perf_counter() - started)
        raise

@router.get('/conversations', response_model=list[ConversationResponse])
def conversations(user: User=Depends(current_user), db: Session=Depends(get_db)):
    # The workspace only needs a bounded recent history for initial render. A
    # composite index avoids sorting an ever-growing account history on login.
    shared_org_folders = select(Conversation.id).join(KnowledgeBase, KnowledgeBase.id == Conversation.knowledge_base_id).join(OrganizationMember, OrganizationMember.organization_id == KnowledgeBase.organization_id).where(OrganizationMember.user_id == user.id, Conversation.visibility == 'shared')
    rows = db.scalars(select(Conversation).where((Conversation.user_id == user.id) | Conversation.id.in_(shared_org_folders)).order_by(Conversation.is_pinned.desc(), Conversation.created_at.desc()).limit(200)).all()
    return [conversation for conversation in rows if can(user, 'read', conversation, db)]

@router.patch('/conversations/{conversation_id}', response_model=ConversationResponse)
def update_conversation(conversation_id: UUID, data: ConversationUpdate, user: User=Depends(current_user), db: Session=Depends(get_db)):
    conversation = db.get(Conversation, conversation_id)
    if conversation and not can(user, 'manage_folders', conversation, db):
        conversation = None
    if conversation is None:
        raise HTTPException(404, 'Conversation not found')
    changes = data.model_dump(exclude_unset=True)
    if changes.get('visibility') == 'shared':
        kb = db.get(KnowledgeBase, conversation.knowledge_base_id) if conversation.knowledge_base_id else None
        if not kb or not kb.organization_id:
            raise HTTPException(422, 'Only organization conversations can be shared.')
    for key, value in changes.items():
        if value is not None:
            setattr(conversation, key, value)
    db.commit()
    db.refresh(conversation)
    return conversation

@router.delete('/conversations/{conversation_id}', status_code=204)
def delete_conversation(conversation_id: UUID, user: User=Depends(current_user), db: Session=Depends(get_db)):
    conversation = db.get(Conversation, conversation_id)
    if conversation and not can(user, 'manage_folders', conversation, db):
        conversation = None
    if conversation is None:
        raise HTTPException(404, 'Conversation not found')
    kb = db.get(KnowledgeBase, conversation.knowledge_base_id) if conversation.knowledge_base_id else None
    if kb and kb.organization_id:
        db.add(AuditEvent(organization_id=kb.organization_id, actor_user_id=user.id, action='conversation_deleted', resource_type='conversation', resource_id=str(conversation.id), details={'title': conversation.title}))
    db.delete(conversation)
    db.commit()

@router.get('/conversations/{conversation_id}/messages', response_model=list[MessageResponse])
def messages(conversation_id: UUID, user: User=Depends(current_user), db: Session=Depends(get_db)):
    conversation = db.get(Conversation, conversation_id)
    if conversation and not can(user, 'read', conversation, db): conversation = None
    if not conversation:
        raise HTTPException(404, 'Conversation not found')
    saved_messages = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.message_index, Message.created_at)
    ).all()
    response = []
    for message in saved_messages:
        try:
            sources = json.loads(message.sources_json) if message.sources_json else []
        except (TypeError, json.JSONDecodeError):
            sources = []
        try:
            metadata = json.loads(message.metadata_json) if message.metadata_json else {}
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        actor = db.get(User, message.actor_user_id) if message.actor_user_id else None
        feedback_status = db.scalar(select(AnswerFeedback.rating).where(
            AnswerFeedback.user_id == user.id, AnswerFeedback.assistant_message_id == message.id).limit(1)) if message.role == 'assistant' else None
        response.append(MessageResponse(
            id=message.id,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
            sources=sources,
            metadata=metadata if isinstance(metadata, dict) else {},
            actor_user_id=message.actor_user_id,
            actor_name=actor.full_name if actor else None,
            actor_email=actor.email if actor else None,
            feedback_status=feedback_status,
        ))
    return response

@router.post('/messages/{assistant_message_id}/feedback')
def submit_answer_feedback(assistant_message_id: UUID, data: AnswerFeedbackRequest,
                           user: User=Depends(current_user), db: Session=Depends(get_db)):
    assistant = db.get(Message, assistant_message_id)
    conversation = db.get(Conversation, assistant.conversation_id) if assistant else None
    if not assistant or assistant.role != 'assistant' or not conversation or not can(user, 'read', conversation, db):
        raise HTTPException(404, 'Answer not found.')
    question = db.scalar(select(Message).where(Message.conversation_id == conversation.id,
        Message.role == 'user', Message.message_index < assistant.message_index)
        .order_by(Message.message_index.desc()).limit(1))
    if not question:
        raise HTTPException(409, 'The question for this answer could not be found.')
    record = db.scalar(select(AnswerFeedback).where(AnswerFeedback.user_id == user.id,
        AnswerFeedback.assistant_message_id == assistant.id).with_for_update())
    if record is None:
        record = AnswerFeedback(user_id=user.id, assistant_message_id=assistant.id,
            conversation_id=conversation.id, question=question.content, answer=assistant.content,
            sources_json=assistant.sources_json or '[]', model_version=assistant.model_name or 'unknown',
            rating=data.rating, comment=data.comment, status='new')
        db.add(record)
    else:
        record.rating, record.comment = data.rating, data.comment
        record.status, record.review_note, record.reviewed_at = 'new', None, None
        record.reviewed_by_user_id = None
    db.commit()
    return {'id': record.id, 'rating': record.rating, 'status': record.status}

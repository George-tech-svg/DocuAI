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
from app.services.llm import answer_question, rewrite_follow_up_question
router = APIRouter(tags=['Chat'])
logger = logging.getLogger(__name__)

class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    is_archived: bool | None = None
    is_pinned: bool | None = None

def _resolve_scope(db, user_id, data: ChatRequest):
    if data.scope_type == 'folder':
        knowledge_base_id = data.scope_id
        document_id = None
        owned_kb(db, user_id, knowledge_base_id)
    else:
        document = db.scalar(select(Document).where(Document.id == data.scope_id))
        if document is None:
            raise HTTPException(404, 'Document not found')
        knowledge_base_id = document.knowledge_base_id
        document_id = document.id
        owned_document(db, user_id, knowledge_base_id, document_id)
    conversation = None
    if data.conversation_id:
        conversation = db.scalar(select(Conversation).where(
            Conversation.id == data.conversation_id,
            Conversation.user_id == user_id,
            Conversation.knowledge_base_id == knowledge_base_id,
            Conversation.document_id == document_id,
            Conversation.scope_type == data.scope_type,
        ))
        if conversation is None:
            raise HTTPException(404, 'Conversation not found')
    if data.scope_type == 'folder' and db.scalar(select(Document.id).where(
        Document.knowledge_base_id == knowledge_base_id,
        Document.status == 'ready',
    ).limit(1)) is None:
        raise HTTPException(400, 'This folder has no ready documents yet. Upload a PDF or TXT file and wait until it is ready before chatting.')
    return knowledge_base_id, document_id, conversation

def _load_follow_up_context(user_id, data: ChatRequest):
    """Validate the requested scope and load recent turns before query rewriting."""
    with sessionmaker(bind=get_engine())() as db:
        _, _, conversation = _resolve_scope(db, user_id, data)
        if conversation is None:
            return []
        recent = db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.message_index.desc(), Message.created_at.desc())
            .limit(8)
        ).all()
        return [{'role': item.role, 'content': item.content} for item in reversed(recent)]

def _prepare_chat(user_id, data: ChatRequest, search_query, query_vector):
    """Run chat authorization and retrieval in one worker-owned DB session."""
    with sessionmaker(bind=get_engine())() as db:
        knowledge_base_id, document_id, conversation = _resolve_scope(db, user_id, data)
        hits, retrieval_details = retrieve(db, knowledge_base_id, search_query, query_vector=query_vector, document_id=document_id, limit=5)
        has_processing_documents = db.scalar(select(Document.id).where(
            Document.knowledge_base_id == knowledge_base_id,
            Document.status.in_(['pending', 'processing']),
        ).limit(1)) is not None
        sources = [Source(document_id=doc_id, filename=name, page_number=chunk.page_number, excerpt=chunk.content[:300]) for chunk, name, doc_id in hits]
        context = '\n\n'.join((f'[{i}] {name}, page {chunk.page_number}: {chunk.content}' for i, (chunk, name, _) in enumerate(hits, 1)))
        return conversation.id if conversation else None, knowledge_base_id, document_id, sources, context, bool(hits), has_processing_documents, retrieval_details

def _save_chat(user_id, knowledge_base_id, document_id, scope_type, conversation_id, question, search_query, answer, sources):
    """Persist the completed exchange in a session owned by this worker."""
    with sessionmaker(bind=get_engine())() as db:
        if conversation_id:
            conversation = db.scalar(select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
                Conversation.knowledge_base_id == knowledge_base_id,
                Conversation.document_id == document_id,
                Conversation.scope_type == scope_type,
            ).with_for_update())
            if conversation is None:
                raise HTTPException(404, 'Conversation not found')
        else:
            conversation = Conversation(
                user_id=user_id,
                knowledge_base_id=knowledge_base_id,
                document_id=document_id,
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
            content=question,
            metadata_json=json.dumps({'search_query': search_query}),
        ))
        db.add(Message(
            conversation_id=conversation.id,
            message_index=next_message_index + 1,
            role='assistant',
            content=answer,
            sources_json=json.dumps([s.model_dump(mode='json') for s in sources]),
        ))
        db.commit()
        return conversation.id

@router.post('/chat', response_model=ChatResponse)
async def chat(data: ChatRequest, user: User=Depends(subscribed_user)):
    started = perf_counter()
    try:
        stage_started = perf_counter()
        recent_messages = await run_in_threadpool(_load_follow_up_context, user.id, data)
        search_query = await rewrite_follow_up_question(data.question, recent_messages)
        logger.warning('Follow-up query preparation completed in %.1f seconds (%s prior message(s)).', perf_counter() - stage_started, len(recent_messages))
        stage_started = perf_counter()
        query_vector = (await run_in_threadpool(embed_texts, [search_query]))[0]
        logger.warning('Chat query embedding completed in %.1f seconds.', perf_counter() - stage_started)
        stage_started = perf_counter()
        conversation_id, knowledge_base_id, document_id, sources, context, has_hits, has_processing_documents, retrieval_details = await run_in_threadpool(
            _prepare_chat, user.id, data, search_query, query_vector
        )
        logger.warning(
            'Chat retrieval completed in %.1f seconds (%s source(s)); path=%s, top-five contributions vector=%s keyword=%s.',
            perf_counter() - stage_started, len(sources), retrieval_details['path'],
            retrieval_details['vector_top_five'], retrieval_details['keyword_top_five'],
        )
        stage_started = perf_counter()
        if has_hits:
            answer = await answer_question(data.question, context)
        elif has_processing_documents:
            answer = 'Your document is still being processed and is not searchable yet. Please wait until its status changes to ready, then ask again.'
        else:
            answer = 'No searchable document content found in this knowledge base. Check that an uploaded document has status ready.'
        logger.warning('Chat answer generation completed in %.1f seconds.', perf_counter() - stage_started)
        stage_started = perf_counter()
        saved_conversation_id = await run_in_threadpool(
            _save_chat, user.id, knowledge_base_id, document_id, data.scope_type, conversation_id,
            data.question, search_query, answer, sources,
        )
        logger.warning('Chat persistence completed in %.1f seconds; total %.1f seconds.', perf_counter() - stage_started, perf_counter() - started)
        return ChatResponse(answer=answer, conversation_id=saved_conversation_id, sources=sources)
    except Exception:
        logger.exception('Chat request failed for user %s and scope %s after %.1f seconds.', user.id, data.scope_id, perf_counter() - started)
        raise

@router.get('/conversations', response_model=list[ConversationResponse])
def conversations(user: User=Depends(current_user), db: Session=Depends(get_db)):
    return list(db.scalars(select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.is_pinned.desc(), Conversation.created_at.desc())).all())

@router.patch('/conversations/{conversation_id}', response_model=ConversationResponse)
def update_conversation(conversation_id: UUID, data: ConversationUpdate, user: User=Depends(current_user), db: Session=Depends(get_db)):
    conversation = db.scalar(select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user.id))
    if conversation is None:
        raise HTTPException(404, 'Conversation not found')
    for key, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(conversation, key, value)
    db.commit()
    db.refresh(conversation)
    return conversation

@router.delete('/conversations/{conversation_id}', status_code=204)
def delete_conversation(conversation_id: UUID, user: User=Depends(current_user), db: Session=Depends(get_db)):
    conversation = db.scalar(select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user.id))
    if conversation is None:
        raise HTTPException(404, 'Conversation not found')
    db.delete(conversation)
    db.commit()

@router.get('/conversations/{conversation_id}/messages', response_model=list[MessageResponse])
def messages(conversation_id: UUID, user: User=Depends(current_user), db: Session=Depends(get_db)):
    conversation = db.scalar(select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user.id))
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
        response.append(MessageResponse(
            id=message.id,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
            sources=sources,
            metadata=metadata if isinstance(metadata, dict) else {},
        ))
    return response

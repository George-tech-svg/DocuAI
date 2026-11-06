"""Chat with indexed documents and save conversation history."""

import json
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.dependencies import current_user
from app.models.user import User
from app.models.conversation import Conversation
from app.models.message import Message
from app.schemas.chat import ChatRequest, ChatResponse, Source, ConversationResponse, MessageResponse
from app.services.document_service import owned_kb
from app.services.retrieval import retrieve
from app.services.llm import answer_question
router = APIRouter(tags=['Chat'])

@router.post('/chat', response_model=ChatResponse)
async def chat(data: ChatRequest, user: User=Depends(current_user), db: Session=Depends(get_db)):
    owned_kb(db, user.id, data.knowledge_base_id)
    conversation = None
    if data.conversation_id:
        conversation = db.scalar(select(Conversation).where(Conversation.id == data.conversation_id, Conversation.user_id == user.id, Conversation.knowledge_base_id == data.knowledge_base_id))
        if conversation is None:
            raise HTTPException(404, 'Conversation not found')
    hits = retrieve(db, data.knowledge_base_id, data.question)
    sources = [Source(document_id=doc_id, filename=name, page_number=chunk.page_number, excerpt=chunk.content[:300]) for chunk, name, doc_id in hits]
    context = '\n\n'.join((f'[{i}] {name}, page {chunk.page_number}: {chunk.content}' for i, (chunk, name, _) in enumerate(hits, 1)))
    answer = await answer_question(data.question, context) if hits else 'No searchable document content found in this knowledge base.'
    if conversation is None:
        conversation = Conversation(user_id=user.id, knowledge_base_id=data.knowledge_base_id, title=data.question[:100])
        db.add(conversation)
        db.flush()
    db.add(Message(conversation_id=conversation.id, role='user', content=data.question))
    db.add(Message(conversation_id=conversation.id, role='assistant', content=answer, sources_json=json.dumps([s.model_dump(mode='json') for s in sources])))
    db.commit()
    return ChatResponse(answer=answer, conversation_id=conversation.id, sources=sources)

@router.get('/conversations', response_model=list[ConversationResponse])
def conversations(user: User=Depends(current_user), db: Session=Depends(get_db)):
    return list(db.scalars(select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.created_at.desc())).all())

@router.get('/conversations/{conversation_id}/messages', response_model=list[MessageResponse])
def messages(conversation_id: UUID, user: User=Depends(current_user), db: Session=Depends(get_db)):
    conversation = db.scalar(select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user.id))
    if not conversation:
        raise HTTPException(404, 'Conversation not found')
    return list(db.scalars(select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)).all())

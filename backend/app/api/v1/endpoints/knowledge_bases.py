"""HTTP endpoints for the current user’s knowledge bases."""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.dependencies import current_user
from app.models.user import User
from app.schemas.knowledge_base import KnowledgeBaseCreate, KnowledgeBaseUpdate, KnowledgeBaseResponse, KnowledgeBaseListResponse
from app.services.knowledge_base_service import create_knowledge_base, list_knowledge_bases, get_knowledge_base, update_knowledge_base, delete_knowledge_base, KnowledgeBaseNotFoundError
router = APIRouter(prefix='/knowledge-bases', tags=['Knowledge Bases'])

@router.post('', response_model=KnowledgeBaseResponse, status_code=201)
def create(data: KnowledgeBaseCreate, user: User=Depends(current_user), db: Session=Depends(get_db)):
    return create_knowledge_base(db, user.id, data)

@router.get('', response_model=KnowledgeBaseListResponse)
def listing(user: User=Depends(current_user), db: Session=Depends(get_db)):
    items = list_knowledge_bases(db, user.id)
    return KnowledgeBaseListResponse(items=items, total=len(items))

@router.get('/{kb_id}', response_model=KnowledgeBaseResponse)
def get(kb_id: UUID, user: User=Depends(current_user), db: Session=Depends(get_db)):
    try:
        return get_knowledge_base(db, user.id, kb_id)
    except KnowledgeBaseNotFoundError:
        raise HTTPException(404, 'Knowledge base not found')

@router.patch('/{kb_id}', response_model=KnowledgeBaseResponse)
def update(kb_id: UUID, data: KnowledgeBaseUpdate, user: User=Depends(current_user), db: Session=Depends(get_db)):
    try:
        return update_knowledge_base(db, user.id, kb_id, data)
    except KnowledgeBaseNotFoundError:
        raise HTTPException(404, 'Knowledge base not found')

@router.delete('/{kb_id}', status_code=204)
def delete(kb_id: UUID, user: User=Depends(current_user), db: Session=Depends(get_db)):
    try:
        delete_knowledge_base(db, user.id, kb_id)
    except KnowledgeBaseNotFoundError:
        raise HTTPException(404, 'Knowledge base not found')
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc

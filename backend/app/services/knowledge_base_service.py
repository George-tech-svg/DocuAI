"""Manage knowledge bases while enforcing user ownership."""

from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.knowledge_base import KnowledgeBase
from app.schemas.knowledge_base import KnowledgeBaseCreate, KnowledgeBaseUpdate
from app.services.storage import delete_file

class KnowledgeBaseNotFoundError(Exception):
    pass

def get_knowledge_base(db: Session, user_id: UUID, knowledge_base_id: UUID):
    kb = db.scalar(select(KnowledgeBase).where(KnowledgeBase.id == knowledge_base_id, KnowledgeBase.user_id == user_id))
    if kb is None:
        raise KnowledgeBaseNotFoundError()
    return kb

def create_knowledge_base(db: Session, user_id: UUID, data: KnowledgeBaseCreate):
    kb = KnowledgeBase(user_id=user_id, **data.model_dump())
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return kb

def list_knowledge_bases(db: Session, user_id: UUID):
    return list(db.scalars(select(KnowledgeBase).where(KnowledgeBase.user_id == user_id).order_by(KnowledgeBase.created_at.desc())).all())

def update_knowledge_base(db: Session, user_id: UUID, knowledge_base_id: UUID, data: KnowledgeBaseUpdate):
    kb = get_knowledge_base(db, user_id, knowledge_base_id)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(kb, k, v)
    db.commit()
    db.refresh(kb)
    return kb

def delete_knowledge_base(db: Session, user_id: UUID, knowledge_base_id: UUID):
    kb = get_knowledge_base(db, user_id, knowledge_base_id)
    # Remove external originals before cascading their Neon metadata/chunks.
    # Keep the knowledge base intact if Cloudinary cannot complete deletion.
    for document in kb.documents:
        if document.cloudinary_public_id:
            try:
                delete_file(document.cloudinary_public_id, document.cloudinary_resource_type or 'raw')
            except Exception as exc:
                raise RuntimeError('Could not delete all original files from Cloudinary') from exc
    db.delete(kb)
    db.commit()

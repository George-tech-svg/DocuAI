"""Manage knowledge bases while enforcing user ownership."""

from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.knowledge_base import KnowledgeBase
from app.models.conversation import Conversation
from app.schemas.knowledge_base import KnowledgeBaseCreate, KnowledgeBaseUpdate
from app.services.storage import delete_file
from app.models.entities import User, Organization, OrganizationMember, AuditEvent
from app.services.permissions import can, require_organization_role

class KnowledgeBaseNotFoundError(Exception):
    pass

def get_knowledge_base(db: Session, user_id: UUID, knowledge_base_id: UUID):
    kb = db.get(KnowledgeBase, knowledge_base_id)
    user = db.get(User, user_id)
    if kb is None or user is None or not can(user, 'read', kb, db):
        raise KnowledgeBaseNotFoundError()
    return kb

def create_knowledge_base(db: Session, user_id: UUID, data: KnowledgeBaseCreate):
    user = db.get(User, user_id)
    organization_id = getattr(data, 'organization_id', None)
    if organization_id:
        organization = db.get(Organization, organization_id)
        if not organization or not can(user, 'manage_folders', organization, db):
            raise KnowledgeBaseNotFoundError()
    kb = KnowledgeBase(user_id=user_id, organization_id=organization_id, name=data.name,
        description=data.description, is_sensitive=getattr(data, 'is_sensitive', False))
    db.add(kb)
    db.flush()
    if organization_id:
        db.add(AuditEvent(organization_id=organization_id, actor_user_id=user_id, action='folder_created', resource_type='knowledge_base', resource_id=str(kb.id), details={'name': kb.name}))
    db.commit()
    db.refresh(kb)
    return kb

def list_knowledge_bases(db: Session, user_id: UUID):
    org_ids = select(OrganizationMember.organization_id).where(OrganizationMember.user_id == user_id)
    user = db.get(User, user_id)
    candidates = db.scalars(select(KnowledgeBase).where((KnowledgeBase.user_id == user_id) | KnowledgeBase.organization_id.in_(org_ids)).order_by(KnowledgeBase.is_pinned.desc(), KnowledgeBase.created_at.desc())).all()
    return [folder for folder in candidates if user and can(user, 'read', folder, db)]

def update_knowledge_base(db: Session, user_id: UUID, knowledge_base_id: UUID, data: KnowledgeBaseUpdate):
    kb = get_knowledge_base(db, user_id, knowledge_base_id)
    user = db.get(User, user_id)
    if not can(user, 'manage_folders', kb, db): raise KnowledgeBaseNotFoundError()
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(kb, k, v)
    db.commit()
    db.refresh(kb)
    return kb

def delete_knowledge_base(db: Session, user_id: UUID, knowledge_base_id: UUID):
    kb = get_knowledge_base(db, user_id, knowledge_base_id)
    user = db.get(User, user_id)
    if not can(user, 'manage_folders', kb, db): raise KnowledgeBaseNotFoundError()
    # Remove external originals before cascading their Neon metadata/chunks.
    # Keep the knowledge base intact if Cloudinary cannot complete deletion.
    for document in kb.documents:
        if document.cloudinary_public_id:
            try:
                delete_file(document.cloudinary_public_id, document.cloudinary_resource_type or 'raw')
            except Exception as exc:
                raise RuntimeError('Could not delete all original files from Cloudinary') from exc
    for conversation in list(kb.conversations):
        db.delete(conversation)
    if kb.organization_id:
        db.add(AuditEvent(organization_id=kb.organization_id, actor_user_id=user_id, action='folder_deleted', resource_type='knowledge_base', resource_id=str(kb.id), details={'name': kb.name}))
    db.delete(kb)
    db.commit()

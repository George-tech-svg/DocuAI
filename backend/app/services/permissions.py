"""Central authorization for personal and organization-owned resources."""
from sqlalchemy import select
from app.models.entities import AuditEvent, Conversation, Document, DocumentEvent, KnowledgeBase, Organization, OrganizationMember

ROLE_ACTIONS = {
    'owner': frozenset({'read', 'chat', 'upload', 'manage_folders', 'manage_members', 'manage_billing', 'delete_organization'}),
    'admin': frozenset({'read', 'chat', 'upload', 'manage_folders', 'manage_members'}),
    'member': frozenset({'read', 'chat', 'upload'}),
    'viewer': frozenset({'read', 'chat'}),
}
ALL_ACTIONS = frozenset({'read', 'chat', 'upload', 'manage_folders', 'manage_members', 'manage_billing', 'delete_organization'})

def role_allows(role: str, action: str) -> bool:
    return action in ROLE_ACTIONS.get(role, ())

def _organization_for(db, resource):
    if isinstance(resource, Organization): return resource
    if isinstance(resource, OrganizationMember): return db.get(Organization, resource.organization_id)
    if isinstance(resource, AuditEvent): return db.get(Organization, resource.organization_id)
    if isinstance(resource, KnowledgeBase):
        return db.get(Organization, resource.organization_id) if resource.organization_id else None
    if isinstance(resource, Document):
        kb = db.get(KnowledgeBase, resource.knowledge_base_id)
        return _organization_for(db, kb) if kb else None
    if isinstance(resource, Conversation):
        if resource.knowledge_base_id:
            kb = db.get(KnowledgeBase, resource.knowledge_base_id)
            return _organization_for(db, kb) if kb else None
        return None
    if isinstance(resource, DocumentEvent):
        if resource.organization_id:
            return db.get(Organization, resource.organization_id)
        document = db.get(Document, resource.document_id)
        return _organization_for(db, document) if document else None
    return None

def can(user, action: str, resource, db) -> bool:
    """Answer whether user may perform action on a model resource.

    Legacy personal resources remain owned by their original user_id. Organization
    resources use the single membership role matrix above.
    """
    if action not in {'read', 'chat', 'upload', 'manage_folders', 'manage_members', 'manage_billing', 'delete_organization'}:
        return False
    if isinstance(resource, Conversation):
        if resource.visibility == 'private':
            return resource.user_id == user.id and action in ROLE_ACTIONS['owner']
        if resource.user_id == user.id and action in {'manage_folders'}:
            return True
        organization = _organization_for(db, resource)
        if organization:
            role = db.scalar(select(OrganizationMember.role).where(OrganizationMember.organization_id == organization.id, OrganizationMember.user_id == user.id))
            return bool(role and role_allows(role, action))
        return resource.user_id == user.id and action in ROLE_ACTIONS['owner']
    organization = _organization_for(db, resource)
    if organization:
        role = db.scalar(select(OrganizationMember.role).where(
            OrganizationMember.organization_id == organization.id,
            OrganizationMember.user_id == user.id,
        ))
        return bool(role and role_allows(role, action))
    if isinstance(resource, KnowledgeBase):
        return resource.user_id == user.id and action in ROLE_ACTIONS['owner']
    if isinstance(resource, Document):
        kb = db.get(KnowledgeBase, resource.knowledge_base_id)
        return bool(kb and can(user, action, kb, db))
    if isinstance(resource, DocumentEvent):
        document = db.get(Document, resource.document_id)
        if document: return can(user, action, document, db)
        return resource.user_id == user.id and action in ROLE_ACTIONS['owner']
    if isinstance(resource, AuditEvent): return False
    if isinstance(resource, Organization): return False
    return False

def require(user, action: str, resource, db, detail: str = 'You do not have permission to perform this action.'):
    if not can(user, action, resource, db):
        from fastapi import HTTPException
        raise HTTPException(404, 'Resource not found or access denied.')
    return resource

def require_organization_role(user, action: str, organization: Organization, db):
    if not can(user, action, organization, db):
        from fastapi import HTTPException
        raise HTTPException(403, 'Your organization role does not allow this action.')
    return organization

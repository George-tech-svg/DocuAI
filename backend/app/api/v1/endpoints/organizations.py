"""Organization workspace, membership, invitation, and append-only audit APIs."""
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import hashlib
import os
import secrets
import smtplib
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.api.dependencies import current_user
from app.db.session import get_db
from app.models.entities import AuditEvent, Conversation, Document, KnowledgeBase, Organization, OrganizationInvite, OrganizationMember, Subscription, SubscriptionPlan, User
from app.models.user import User as UserModel
from app.services.permissions import can, require_organization_role

router = APIRouter(prefix='/organizations', tags=['Organizations'])
ORG_TYPES = {'business', 'school', 'sacco', 'ngo', 'law_firm', 'other'}
ROLES = {'owner', 'admin', 'member', 'viewer'}
INVITE_ROLES = {'admin', 'member', 'viewer'}

class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    type: str

class InviteCreate(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    role: str = 'member'

class RoleUpdate(BaseModel):
    role: str

class ExportAuditRequest(BaseModel):
    resource_type: str
    resource_id: UUID | None = None

class RetentionUpdate(BaseModel):
    retention_days: int | None = Field(default=None, ge=1, le=3650)

def _audit(db, org_id, actor_id, action, resource_type, resource_id=None, details=None):
    db.add(AuditEvent(organization_id=org_id, actor_user_id=actor_id, action=action,
        resource_type=resource_type, resource_id=str(resource_id) if resource_id else None, details=details or {}))

def _org(db, org_id, user, action='read'):
    org = db.get(Organization, org_id)
    if not org: raise HTTPException(404, 'Organization not found.')
    require_organization_role(user, action, org, db)
    return org

def _send_invite(email, organization_name, link):
    host = os.getenv('SMTP_HOST', '').strip()
    if not host: raise HTTPException(503, 'Organization invitations need SMTP_HOST, SMTP_FROM, SMTP_USER, and SMTP_PASSWORD configured on the backend.')
    message = EmailMessage()
    message['Subject'] = f'Invitation to join {organization_name} on DocuMind AI'
    message['From'] = os.getenv('SMTP_FROM', os.getenv('SMTP_USER', ''))
    message['To'] = email
    message.set_content(f'You have been invited to join {organization_name} on DocuMind AI. Sign in or create an account with this email, then open this invitation link:\n\n{link}\n\nThis link expires in 7 days.')
    with smtplib.SMTP(host, int(os.getenv('SMTP_PORT', '587')), timeout=15) as smtp:
        if os.getenv('SMTP_STARTTLS', 'true').lower() in {'1', 'true', 'yes'}: smtp.starttls()
        username, password = os.getenv('SMTP_USER', ''), os.getenv('SMTP_PASSWORD', '')
        if username: smtp.login(username, password)
        smtp.send_message(message)

@router.get('')
def my_organizations(user: UserModel = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Organization, OrganizationMember.role).join(OrganizationMember).where(OrganizationMember.user_id == user.id).order_by(Organization.name)).all()
    return [{'id': org.id, 'name': org.name, 'type': org.type, 'role': role,
             'retention_days':org.retention_days} for org, role in rows]

@router.post('', status_code=201)
def create_organization(data: OrganizationCreate, user: UserModel = Depends(current_user), db: Session = Depends(get_db)):
    if data.type not in ORG_TYPES: raise HTTPException(422, 'Choose a valid organization type.')
    org = Organization(name=data.name.strip(), type=data.type, created_by=user.id)
    db.add(org); db.flush()
    db.add(OrganizationMember(organization_id=org.id, user_id=user.id, role='owner'))
    _audit(db, org.id, user.id, 'organization_created', 'organization', org.id, {'name': org.name})
    db.commit(); db.refresh(org)
    return {'id': org.id, 'name': org.name, 'type': org.type, 'role': 'owner'}

@router.get('/invites/{token}')
def invite_preview(token: str, db: Session = Depends(get_db)):
    digest = hashlib.sha256(token.encode()).hexdigest()
    invite = db.scalar(select(OrganizationInvite).where(OrganizationInvite.token_hash == digest))
    if not invite or invite.status != 'pending' or invite.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(404, 'This invitation is invalid, expired, or already used.')
    org = db.get(Organization, invite.organization_id)
    return {'organization_name': org.name if org else 'Organization', 'email': invite.email, 'role': invite.role, 'expires_at': invite.expires_at}

@router.post('/invites/{token}/accept')
def accept_invite(token: str, user: UserModel = Depends(current_user), db: Session = Depends(get_db)):
    digest = hashlib.sha256(token.encode()).hexdigest()
    invite = db.scalar(select(OrganizationInvite).where(OrganizationInvite.token_hash == digest).with_for_update())
    now = datetime.now(timezone.utc)
    if not invite or invite.status != 'pending' or invite.expires_at <= now:
        if invite and invite.status == 'pending': invite.status = 'expired'; db.commit()
        raise HTTPException(404, 'This invitation is invalid, expired, or already used.')
    if invite.email.casefold() != user.email.casefold(): raise HTTPException(403, 'Sign in with the email address this invitation was sent to.')
    active_sub = db.scalar(select(Subscription).where(Subscription.organization_id == invite.organization_id, Subscription.status == 'active', Subscription.starts_at <= now, Subscription.expires_at > now).order_by(Subscription.expires_at.desc()).limit(1))
    member_count = db.scalar(select(func.count(OrganizationMember.id)).where(OrganizationMember.organization_id == invite.organization_id)) or 0
    if active_sub and active_sub.seat_limit is not None and member_count >= active_sub.seat_limit:
        raise HTTPException(409, 'This organization has reached its subscription seat limit. Ask an owner to add seats before accepting.')
    if not db.scalar(select(OrganizationMember.id).where(OrganizationMember.organization_id == invite.organization_id, OrganizationMember.user_id == user.id)):
        db.add(OrganizationMember(organization_id=invite.organization_id, user_id=user.id, role=invite.role))
    invite.status = 'accepted'
    _audit(db, invite.organization_id, user.id, 'member_joined', 'organization_invite', invite.id, {'email': user.email, 'role': invite.role})
    db.commit()
    org = db.get(Organization, invite.organization_id)
    return {'organization_id': org.id, 'organization_name': org.name, 'role': invite.role, 'message': f'You joined {org.name}.'}

@router.get('/{organization_id}')
def organization_detail(organization_id: UUID, user: UserModel = Depends(current_user), db: Session = Depends(get_db)):
    org = _org(db, organization_id, user)
    role = db.scalar(select(OrganizationMember.role).where(OrganizationMember.organization_id == org.id, OrganizationMember.user_id == user.id))
    member_count = db.scalar(select(func.count(OrganizationMember.id)).where(OrganizationMember.organization_id == org.id)) or 0
    return {'id': org.id, 'name': org.name, 'type': org.type, 'role': role,
            'member_count': member_count, 'retention_days':org.retention_days}

@router.patch('/{organization_id}/retention')
def update_retention(organization_id: UUID, data: RetentionUpdate,
                     user: UserModel = Depends(current_user), db: Session = Depends(get_db)):
    org = _org(db, organization_id, user, 'manage_folders')
    org.retention_days = data.retention_days
    _audit(db, org.id, user.id, 'retention_policy_changed', 'organization', org.id,
        {'retention_days':data.retention_days})
    db.commit()
    return {'organization_id':org.id,'retention_days':org.retention_days}

@router.get('/{organization_id}/members')
def list_members(organization_id: UUID, user: UserModel = Depends(current_user), db: Session = Depends(get_db)):
    org = _org(db, organization_id, user)
    rows = db.execute(select(OrganizationMember, User).join(User, User.id == OrganizationMember.user_id).where(OrganizationMember.organization_id == org.id).order_by(OrganizationMember.joined_at)).all()
    return [{'id': member.id, 'user_id': account.id, 'name': account.full_name, 'email': account.email, 'role': member.role, 'joined_at': member.joined_at} for member, account in rows]

@router.post('/{organization_id}/invites', status_code=201)
def create_invite(organization_id: UUID, data: InviteCreate, user: UserModel = Depends(current_user), db: Session = Depends(get_db)):
    org = _org(db, organization_id, user, 'manage_members')
    email = data.email.strip().casefold()
    if data.role not in INVITE_ROLES: raise HTTPException(422, 'Invitations can use admin, member, or viewer roles.')
    member = db.scalar(select(OrganizationMember.id).join(User, User.id == OrganizationMember.user_id).where(OrganizationMember.organization_id == org.id, func.lower(User.email) == email))
    if member: raise HTTPException(409, 'This email is already a member of the organization.')
    now = datetime.now(timezone.utc)
    db.query(OrganizationInvite).filter(OrganizationInvite.organization_id == org.id, func.lower(OrganizationInvite.email) == email, OrganizationInvite.status == 'pending').update({'status': 'revoked'})
    token = secrets.token_urlsafe(32)
    invite = OrganizationInvite(organization_id=org.id, email=email, role=data.role, token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=now + timedelta(days=7), invited_by_user_id=user.id)
    db.add(invite); db.flush()
    origin = os.getenv('FRONTEND_ORIGIN', 'https://docuai-jet.vercel.app').rstrip('/')
    link = f'{origin}/?organization_invite={token}'
    try: _send_invite(email, org.name, link)
    except HTTPException: db.rollback(); raise
    except Exception as exc: db.rollback(); raise HTTPException(502, 'The invitation email could not be sent. Check SMTP settings and try again.') from exc
    _audit(db, org.id, user.id, 'member_invited', 'organization_invite', invite.id, {'email': email, 'role': data.role, 'expires_at': invite.expires_at.isoformat()})
    db.commit()
    return {'id': invite.id, 'email': email, 'role': data.role, 'expires_at': invite.expires_at, 'status': invite.status, 'message': 'Invitation email sent.'}

@router.patch('/{organization_id}/members/{member_id}')
def update_member_role(organization_id: UUID, member_id: UUID, data: RoleUpdate, user: UserModel = Depends(current_user), db: Session = Depends(get_db)):
    org = _org(db, organization_id, user, 'manage_members')
    member = db.scalar(select(OrganizationMember).where(OrganizationMember.id == member_id, OrganizationMember.organization_id == org.id).with_for_update())
    if not member: raise HTTPException(404, 'Organization member not found.')
    if data.role not in ROLES - {'owner'}: raise HTTPException(422, 'Role must be admin, member, or viewer.')
    if member.role == 'owner': raise HTTPException(409, 'Transfer ownership before changing the owner role.')
    if user.id != org.created_by and data.role == 'admin' and db.scalar(select(OrganizationMember.role).where(OrganizationMember.organization_id == org.id, OrganizationMember.user_id == user.id)) != 'owner':
        raise HTTPException(403, 'Only an owner can appoint another administrator.')
    old_role = member.role; member.role = data.role
    account = db.get(User, member.user_id)
    _audit(db, org.id, user.id, 'member_role_changed', 'organization_member', member.id, {'email': account.email if account else None, 'from': old_role, 'to': data.role})
    db.commit()
    return {'id': member.id, 'role': member.role}

@router.delete('/{organization_id}/members/{member_id}', status_code=204)
def remove_member(organization_id: UUID, member_id: UUID, user: UserModel = Depends(current_user), db: Session = Depends(get_db)):
    org = _org(db, organization_id, user, 'manage_members')
    member = db.scalar(select(OrganizationMember).where(OrganizationMember.id == member_id, OrganizationMember.organization_id == org.id).with_for_update())
    if not member: raise HTTPException(404, 'Organization member not found.')
    if member.role == 'owner': raise HTTPException(409, 'The owner cannot be removed. Transfer ownership first.')
    account = db.get(User, member.user_id)
    _audit(db, org.id, user.id, 'member_removed', 'organization_member', member.id, {'email': account.email if account else None, 'role': member.role})
    db.delete(member); db.commit()

@router.get('/{organization_id}/activity')
def organization_activity(organization_id: UUID, user: UserModel = Depends(current_user), db: Session = Depends(get_db)):
    org = _org(db, organization_id, user, 'read')
    rows = db.execute(select(AuditEvent, User).outerjoin(User, User.id == AuditEvent.actor_user_id).where(AuditEvent.organization_id == org.id).order_by(AuditEvent.created_at.desc()).limit(200)).all()
    return [{'id': event.id, 'action': event.action, 'resource_type': event.resource_type, 'resource_id': event.resource_id, 'details': event.details, 'actor_name': actor.full_name if actor else 'Former member', 'actor_email': actor.email if actor else None, 'created_at': event.created_at} for event, actor in rows]

@router.post('/{organization_id}/exports', status_code=201)
def log_export(organization_id: UUID, data: ExportAuditRequest, user: UserModel = Depends(current_user), db: Session = Depends(get_db)):
    org = _org(db, organization_id, user, 'read')
    if data.resource_type == 'document' and data.resource_id:
        resource = db.get(Document, data.resource_id)
    elif data.resource_type == 'conversation' and data.resource_id:
        resource = db.get(Conversation, data.resource_id)
    elif data.resource_type == 'knowledge_base' and data.resource_id:
        resource = db.get(KnowledgeBase, data.resource_id)
    else: raise HTTPException(422, 'Choose a valid organization export resource.')
    if not resource or not can(user, 'read', resource, db) or getattr(resource, 'organization_id', None) != org.id:
        if isinstance(resource, (Document, Conversation)):
            kb = db.get(KnowledgeBase, resource.knowledge_base_id) if resource.knowledge_base_id else None
            if not kb or kb.organization_id != org.id: raise HTTPException(404, 'Export resource not found.')
        else: raise HTTPException(404, 'Export resource not found.')
    _audit(db, org.id, user.id, 'export_created', data.resource_type, data.resource_id, {})
    db.commit()
    return {'status': 'recorded'}

@router.get('/{organization_id}/billing')
def organization_billing(organization_id: UUID, user: UserModel = Depends(current_user), db: Session = Depends(get_db)):
    org = _org(db, organization_id, user, 'manage_billing')
    now = datetime.now(timezone.utc)
    sub = db.scalar(select(Subscription).where(Subscription.organization_id == org.id, Subscription.status == 'active', Subscription.starts_at <= now, Subscription.expires_at > now).order_by(Subscription.expires_at.desc()).limit(1))
    count = db.scalar(select(func.count(OrganizationMember.id)).where(OrganizationMember.organization_id == org.id)) or 0
    plan = db.get(SubscriptionPlan, sub.plan_id) if sub else None
    return {'organization_id': org.id, 'member_count': count, 'seat_limit': sub.seat_limit if sub else None, 'subscription': {'plan_name': plan.name if plan else None, 'status': sub.status, 'expires_at': sub.expires_at} if sub else None}

@router.delete('/{organization_id}', status_code=204)
def delete_organization(organization_id: UUID, user: UserModel = Depends(current_user), db: Session = Depends(get_db)):
    raise HTTPException(409, 'Organization deletion now requires exact-name confirmation and a background cleanup. Use DELETE /api/v1/privacy/organizations/{organization_id}.')

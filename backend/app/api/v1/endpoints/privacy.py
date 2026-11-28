"""Self-service privacy rights, consent history, and provider disclosures."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import (AuditEvent, DataDeletionRequest, DataExportRequest, Job,
    Organization, OrganizationMember, PrivacyConsent, User)

router = APIRouter(prefix='/privacy', tags=['Privacy and data rights'])


class ConsentAccept(BaseModel):
    accept_terms: bool
    accept_privacy: bool


class AccountDeleteConfirm(BaseModel):
    confirmation: str = Field(min_length=10, max_length=40)


class OrganizationDeleteConfirm(BaseModel):
    confirmation: str = Field(min_length=5, max_length=220)


def _acceptance(db: Session, user_id: UUID, policy: str, version: str) -> bool:
    return db.scalar(select(PrivacyConsent.id).where(PrivacyConsent.user_id == user_id,
        PrivacyConsent.policy == policy, PrivacyConsent.version == version).limit(1)) is not None


@router.get('/notices')
def notices():
    settings = get_settings()
    return {
        'terms_version': settings.TERMS_VERSION,
        'privacy_version': settings.PRIVACY_POLICY_VERSION,
        'company_name': 'To be supplied by the platform operator',
        'company_address': 'To be supplied by the platform operator',
        'odpc_registration_number': 'To be supplied if registered or required',
        'providers': [
            {'name':'DeepSeek','purpose':'Receives questions and selected document passages to generate answers and language translations.'},
            {'name':'Cloudinary','purpose':'Stores uploaded original files and temporary privacy export archives.'},
            {'name':'Neon','purpose':'Hosts PostgreSQL account, document metadata, extracted text, conversations, billing and operational records.'},
            {'name':'Vercel','purpose':'Hosts the web interface and routes browser API requests to the backend.'},
            {'name':'Render','purpose':'Runs the backend API and background document, reminder and privacy jobs.'},
            {'name':'Bird','purpose':'Processes WhatsApp messages, linked phone numbers, document attachments and notifications when that channel is used.'},
            {'name':'Safaricom Daraja','purpose':'Processes M-Pesa payment prompts and callbacks, including payer phone and transaction details.'},
        ],
        'notice':'Provider locations, retention periods, transfer terms, and contractual roles must be confirmed from current provider agreements and settings.'
    }


@router.get('/consent/status')
def consent_status(user: User = Depends(current_user), db: Session = Depends(get_db)):
    settings = get_settings()
    terms = _acceptance(db, user.id, 'terms', settings.TERMS_VERSION)
    privacy = _acceptance(db, user.id, 'privacy', settings.PRIVACY_POLICY_VERSION)
    return {'terms_version':settings.TERMS_VERSION, 'privacy_version':settings.PRIVACY_POLICY_VERSION,
            'terms_accepted':terms, 'privacy_accepted':privacy, 'required':not (terms and privacy)}


@router.post('/consent')
def accept_current_notices(data: ConsentAccept, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not data.accept_terms or not data.accept_privacy:
        raise HTTPException(400, 'Accept both the current Terms and Privacy Notice to continue.')
    settings, now = get_settings(), datetime.now(timezone.utc)
    for policy, version in (('terms', settings.TERMS_VERSION), ('privacy', settings.PRIVACY_POLICY_VERSION)):
        if not _acceptance(db, user.id, policy, version):
            db.add(PrivacyConsent(user_id=user.id, policy=policy, version=version, accepted_at=now))
    db.add(AuditEvent(organization_id=None, actor_user_id=user.id, action='current_notices_accepted',
        resource_type='user', resource_id=str(user.id), details={'terms_version':settings.TERMS_VERSION,'privacy_version':settings.PRIVACY_POLICY_VERSION}))
    db.commit()
    return {'required':False,'accepted_at':now}


@router.post('/exports', status_code=202)
def request_personal_export(user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = DataExportRequest(owner_user_id=user.id, requested_by_user_id=user.id, status='queued')
    db.add(row); db.flush()
    db.add(Job(type='export_user_data', payload={'export_id':str(row.id)}, max_attempts=3))
    db.add(AuditEvent(organization_id=None, actor_user_id=user.id, action='personal_data_export_requested',
        resource_type='data_export', resource_id=str(row.id), details={'scope':'personal'}))
    db.commit()
    return {'id':row.id,'status':row.status,'message':'Your export is being prepared. Check this page again shortly.'}


@router.post('/organizations/{organization_id}/exports', status_code=202)
def request_organization_export(organization_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    member = db.scalar(select(OrganizationMember).where(OrganizationMember.organization_id == organization_id,
        OrganizationMember.user_id == user.id, OrganizationMember.role == 'owner'))
    if not member: raise HTTPException(404, 'Organization not found or owner access required.')
    row = DataExportRequest(organization_id=organization_id, requested_by_user_id=user.id, status='queued')
    db.add(row); db.flush()
    db.add(Job(type='export_organization_data', payload={'export_id':str(row.id)}, max_attempts=3))
    db.add(AuditEvent(organization_id=organization_id, actor_user_id=user.id, action='organization_data_export_requested',
        resource_type='data_export', resource_id=str(row.id), details={}))
    db.commit()
    return {'id':row.id,'status':row.status,'message':'The organization export is being prepared.'}


@router.get('/exports/{export_id}')
def get_export(export_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.get(DataExportRequest, export_id)
    if not row or not (row.owner_user_id == user.id or row.requested_by_user_id == user.id):
        raise HTTPException(404, 'Export request not found.')
    result = {'id':row.id,'status':row.status,'error':row.error,'expires_at':row.expires_at}
    if row.status == 'ready' and row.storage_public_id:
        from app.services.storage import private_export_url
        result['download_url'] = private_export_url(row.storage_public_id)
    return result

@router.get('/exports')
def list_personal_exports(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(DataExportRequest).where(DataExportRequest.owner_user_id == user.id)
        .order_by(DataExportRequest.created_at.desc()).limit(20)).all()
    from app.services.storage import private_export_url
    return {'items':[{'id':row.id,'status':row.status,'error':row.error,'created_at':row.created_at,
        'expires_at':row.expires_at,'download_url':private_export_url(row.storage_public_id) if row.status == 'ready' and row.storage_public_id else None} for row in rows]}

@router.get('/organizations/{organization_id}/exports')
def list_organization_exports(organization_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    owner = db.scalar(select(OrganizationMember.id).where(OrganizationMember.organization_id == organization_id,
        OrganizationMember.user_id == user.id, OrganizationMember.role == 'owner'))
    if not owner: raise HTTPException(404, 'Organization not found or owner access required.')
    rows = db.scalars(select(DataExportRequest).where(DataExportRequest.organization_id == organization_id,
        DataExportRequest.requested_by_user_id == user.id).order_by(DataExportRequest.created_at.desc()).limit(20)).all()
    from app.services.storage import private_export_url
    return {'items':[{'id':row.id,'status':row.status,'error':row.error,'created_at':row.created_at,
        'expires_at':row.expires_at,'download_url':private_export_url(row.storage_public_id) if row.status == 'ready' and row.storage_public_id else None} for row in rows]}


@router.delete('/account', status_code=202)
def request_account_deletion(data: AccountDeleteConfirm, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if data.confirmation != 'DELETE MY ACCOUNT':
        raise HTTPException(400, 'Type DELETE MY ACCOUNT exactly to confirm.')
    if user.is_superuser and db.scalar(select(User.id).where(User.is_superuser.is_(True), User.id != user.id).limit(1)) is None:
        raise HTTPException(409, 'You are the only platform administrator. Create another administrator before deleting this account.')
    owned_org = db.scalar(select(Organization).outerjoin(OrganizationMember,
        OrganizationMember.organization_id == Organization.id).where(
        ((OrganizationMember.user_id == user.id) & (OrganizationMember.role == 'owner')) |
        (Organization.created_by == user.id)).limit(1))
    if owned_org:
        raise HTTPException(409, f'Transfer ownership or request deletion of organization “{owned_org.name}” before deleting your account.')
    row = DataDeletionRequest(target_type='account', target_id=user.id, requested_by_user_id=user.id, status='queued')
    db.add(row); db.flush()
    db.add(Job(type='delete_user_data', payload={'deletion_id':str(row.id)}, max_attempts=8))
    # Reference the deletion request instead of repeating a direct account ID
    # in the permanent audit row. The requester FK is nulled on erasure.
    db.add(AuditEvent(organization_id=None, actor_user_id=None, action='account_deletion_requested',
        resource_type='deletion_request', resource_id=str(row.id), details={'request_id':str(row.id)}))
    db.commit()
    return {'id':row.id,'status':'queued','will_delete':['personal folders','original uploaded files','document vectors and extracted text','conversations and messages','reminders and notification preferences','account profile and sign-in factors','WhatsApp link and account-level data'],
            'will_keep':['permanent security and audit records required to record this deletion; identifiers are retained only as audit references']}


@router.delete('/organizations/{organization_id}', status_code=202)
def request_organization_deletion(organization_id: UUID, data: OrganizationDeleteConfirm,
                                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    org = db.get(Organization, organization_id)
    member = db.scalar(select(OrganizationMember).where(OrganizationMember.organization_id == organization_id,
        OrganizationMember.user_id == user.id, OrganizationMember.role == 'owner'))
    if not org or not member: raise HTTPException(404, 'Organization not found or owner access required.')
    if data.confirmation != f'DELETE {org.name}': raise HTTPException(400, f'Type DELETE {org.name} exactly to confirm.')
    row = DataDeletionRequest(target_type='organization', target_id=org.id, requested_by_user_id=user.id, status='queued')
    db.add(row); db.flush()
    db.add(Job(type='delete_organization_data', payload={'deletion_id':str(row.id)}, max_attempts=8))
    db.add(AuditEvent(organization_id=org.id, actor_user_id=user.id, action='organization_deletion_requested',
        resource_type='organization', resource_id=str(org.id), details={'name':org.name,'request_id':str(row.id)}))
    db.commit()
    return {'id':row.id,'status':'queued','will_delete':['organization profile and memberships','organization folders and documents','original files','vectors and extracted text','shared conversations and messages','organization subscriptions and reminders'],
            'will_keep':['append-only audit entries recording the request and completed deletion']}

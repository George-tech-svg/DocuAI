"""Reusable authentication dependencies for protected endpoints."""

from uuid import UUID
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.security import get_token_subject, TokenValidationError
from app.models.user import User
from app.models.entities import Subscription, OrganizationMember
from app.models.entities import PrivacyConsent
from app.core.config import get_settings
from sqlalchemy import select, func, or_, exists
from datetime import datetime, timezone
def current_user(request: Request, db: Session=Depends(get_db)) -> User:
    """Require an HttpOnly cookie session and current notices."""
    from app.services.security_controls import SESSION_COOKIE
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(401, 'Authentication required')
    try:
        user_id = UUID(get_token_subject(token))
    except (ValueError, TokenValidationError):
        raise HTTPException(401, 'Invalid token')
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(401, 'Invalid or inactive account')
    allowed_notice_paths = {'/api/v1/auth/me', '/api/v1/auth/logout', '/api/v1/privacy/notices',
                            '/api/v1/privacy/consent/status', '/api/v1/privacy/consent'}
    path = request.url.path
    if path not in allowed_notice_paths and not path.endswith('/auth/me') and '/privacy/' not in path:
        settings = get_settings()
        policies = [('terms', settings.TERMS_VERSION), ('privacy', settings.PRIVACY_POLICY_VERSION)]
        accepted = all(db.scalar(select(exists().where(PrivacyConsent.user_id == user.id,
            PrivacyConsent.policy == policy, PrivacyConsent.version == version))) for policy, version in policies)
        if not accepted:
            raise HTTPException(428, 'Please review and accept the current Terms and Privacy Notice to continue.')
    return user

def admin_user(user: User=Depends(current_user)) -> User:
    """Require a database-authorized platform administrator."""
    if not user.is_superuser:
        raise HTTPException(403, 'Administrator access required')
    return user

def subscribed_user(user: User=Depends(current_user), db: Session=Depends(get_db)) -> User:
    """Optionally require paid access for metered product operations."""
    if not get_settings().SUBSCRIPTIONS_ENFORCED or user.is_superuser:
        return user
    active = db.scalar(select(Subscription.id).where(
        Subscription.user_id == user.id,
        Subscription.organization_id.is_(None),
        Subscription.status == 'active',
        Subscription.starts_at <= datetime.now(timezone.utc),
        Subscription.expires_at > datetime.now(timezone.utc),
    ).limit(1))
    if active is None:
        seat_count = select(func.count(OrganizationMember.id)).where(OrganizationMember.organization_id == Subscription.organization_id).scalar_subquery()
        active = db.scalar(select(Subscription.id).join(OrganizationMember, OrganizationMember.organization_id == Subscription.organization_id).where(
            OrganizationMember.user_id == user.id,
            Subscription.status == 'active',
            Subscription.starts_at <= datetime.now(timezone.utc),
            Subscription.expires_at > datetime.now(timezone.utc),
            or_(Subscription.seat_limit.is_(None), Subscription.seat_limit >= seat_count),
        ).limit(1))
    if active is None:
        raise HTTPException(402, 'Choose a plan and complete M-Pesa payment to use the chatbot.')
    return user

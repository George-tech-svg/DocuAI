"""Reusable authentication dependencies for protected endpoints."""

from uuid import UUID
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.security import get_token_subject, TokenValidationError
from app.models.user import User
from app.models.entities import Subscription
from app.core.config import get_settings
from sqlalchemy import select
from datetime import datetime, timezone
bearer = HTTPBearer(auto_error=False)

def current_user(credentials: HTTPAuthorizationCredentials | None=Depends(bearer), db: Session=Depends(get_db)) -> User:
    """Require a valid bearer token and an active user account."""
    if not credentials:
        raise HTTPException(401, 'Authentication required', headers={'WWW-Authenticate': 'Bearer'})
    try:
        user_id = UUID(get_token_subject(credentials.credentials))
    except (ValueError, TokenValidationError):
        raise HTTPException(401, 'Invalid token')
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(401, 'Invalid or inactive account')
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
        Subscription.status == 'active',
        Subscription.starts_at <= datetime.now(timezone.utc),
        Subscription.expires_at > datetime.now(timezone.utc),
    ).limit(1))
    if active is None:
        raise HTTPException(402, 'Choose a plan and complete M-Pesa payment to use the chatbot.')
    return user

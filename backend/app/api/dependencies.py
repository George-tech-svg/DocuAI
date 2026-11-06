"""Reusable authentication dependencies for protected endpoints."""

from uuid import UUID
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.security import get_token_subject, TokenValidationError
from app.models.user import User
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

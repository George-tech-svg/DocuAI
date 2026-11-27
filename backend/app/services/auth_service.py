"""Register users and verify their login credentials."""

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models.user import User
from app.schemas.auth import UserRegister
from app.core.security import hash_password, verify_password

class EmailAlreadyRegisteredError(Exception):
    pass

class AuthenticationError(Exception):
    pass

class GoogleOnlyAccountError(AuthenticationError):
    pass

class WrongPasswordError(AuthenticationError):
    pass

def register_user(db: Session, data: UserRegister):
    """Create a new user with a safely hashed password."""
    existing = db.scalar(select(User).where(User.email == data.email.lower()))
    if existing:
        raise EmailAlreadyRegisteredError('google' if existing.password_hash is None else 'password')
    user = User(full_name=data.full_name, email=data.email.lower(), password_hash=hash_password(data.password))
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(User).where(User.email == data.email.lower()))
        raise EmailAlreadyRegisteredError('google' if existing and existing.password_hash is None else 'password')
    return user

def authenticate_user(db: Session, email: str, password: str):
    """Check login credentials without exposing the stored password hash."""
    user = db.scalar(select(User).where(User.email == email.lower()))
    if not user:
        raise AuthenticationError()
    if user.password_hash is None:
        raise GoogleOnlyAccountError()
    if not verify_password(password, user.password_hash):
        raise WrongPasswordError()
    if not user.is_active:
        raise AuthenticationError()
    return user

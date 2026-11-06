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

def register_user(db: Session, data: UserRegister):
    """Create a new user with a safely hashed password."""
    if db.scalar(select(User).where(User.email == data.email.lower())):
        raise EmailAlreadyRegisteredError()
    user = User(full_name=data.full_name, email=data.email.lower(), password_hash=hash_password(data.password))
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise EmailAlreadyRegisteredError()
    return user

def authenticate_user(db: Session, email: str, password: str):
    """Check login credentials without exposing the stored password hash."""
    user = db.scalar(select(User).where(User.email == email.lower()))
    if not user or not verify_password(password, user.password_hash) or (not user.is_active):
        raise AuthenticationError()
    return user

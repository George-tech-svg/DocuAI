"""Register users, sign in, and return the authenticated user profile."""

from fastapi import APIRouter, Depends, HTTPException
import secrets
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.dependencies import current_user
from app.models.user import User
from app.schemas.auth import UserRegister, UserLogin, AdminBootstrapRequest, UserResponse, AuthResponse
from app.services.auth_service import register_user, authenticate_user, EmailAlreadyRegisteredError, AuthenticationError
from app.core.security import create_access_token
from app.core.config import get_settings
from app.core.security import hash_password, verify_password
router = APIRouter(prefix='/auth', tags=['Authentication'])

@router.get('/admin/bootstrap/status')
def admin_bootstrap_status(db: Session=Depends(get_db)):
    """Expose only whether the one-time setup is available, never its secret."""
    available = bool(get_settings().ADMIN_BOOTSTRAP_CODE) and db.scalar(
        select(User.id).where(User.is_superuser.is_(True)).limit(1)
    ) is None
    return {'available': available}

@router.post('/admin/bootstrap', response_model=AuthResponse, status_code=201)
def bootstrap_admin(data: AdminBootstrapRequest, db: Session=Depends(get_db)):
    """Create or promote the first and only super administrator."""
    expected_code = get_settings().ADMIN_BOOTSTRAP_CODE
    if not expected_code or not secrets.compare_digest(data.setup_code, expected_code):
        raise HTTPException(403, 'Administrator setup is unavailable.')

    # Serialize concurrent first-time setup requests so only one can succeed.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('documind_one_time_admin_bootstrap'))"))
    if db.scalar(select(User.id).where(User.is_superuser.is_(True)).limit(1)) is not None:
        db.rollback()
        raise HTTPException(409, 'Administrator setup has already been completed.')

    email = str(data.email).lower()
    user = db.scalar(select(User).where(User.email == email).with_for_update())
    if user:
        if not verify_password(data.password, user.password_hash):
            db.rollback()
            raise HTTPException(401, 'The password does not match this existing account.')
        if not user.is_active:
            db.rollback()
            raise HTTPException(403, 'This account is disabled and cannot become an administrator.')
        user.is_superuser = True
    else:
        user = User(full_name=data.full_name, email=email,
                    password_hash=hash_password(data.password), is_superuser=True)
        db.add(user)
    db.commit()
    db.refresh(user)
    return AuthResponse(user=UserResponse.model_validate(user), access_token=create_access_token(str(user.id)))

@router.post('/register', response_model=AuthResponse, status_code=201)
def register(data: UserRegister, db: Session=Depends(get_db)):
    try:
        user = register_user(db, data)
    except EmailAlreadyRegisteredError:
        raise HTTPException(409, 'Email already registered')
    return AuthResponse(user=UserResponse.model_validate(user), access_token=create_access_token(str(user.id)))

@router.post('/login', response_model=AuthResponse)
def login(data: UserLogin, db: Session=Depends(get_db)):
    try:
        user = authenticate_user(db, data.email, data.password)
    except AuthenticationError:
        raise HTTPException(401, 'Invalid credentials')
    return AuthResponse(user=UserResponse.model_validate(user), access_token=create_access_token(str(user.id)))

@router.get('/me', response_model=UserResponse)
def me(user: User=Depends(current_user)):
    return user

"""Register users, sign in, and return the authenticated user profile."""

from fastapi import APIRouter, Depends, HTTPException
import secrets
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.dependencies import current_user
from app.models.user import User
from app.schemas.auth import UserRegistrationRequest, UserLogin, GoogleLoginRequest, AdminBootstrapRequest, UserResponse, AuthResponse
from app.services.auth_service import register_user, authenticate_user, EmailAlreadyRegisteredError, AuthenticationError, GoogleOnlyAccountError
from app.core.security import create_access_token
from app.core.config import get_settings
from app.core.security import hash_password, verify_password
router = APIRouter(prefix='/auth', tags=['Authentication'])

@router.get('/google/config')
def google_sign_in_config():
    """Return the public Google client ID so sign-in also works without a Vite build variable."""
    client_id = get_settings().GOOGLE_CLIENT_ID.strip()
    return {'enabled': bool(client_id), 'client_id': client_id or None}

@router.get('/admin/bootstrap/status')
def admin_bootstrap_status(db: Session=Depends(get_db)):
    """Expose only whether the one-time setup is available, never its secret."""
    configured = bool(get_settings().ADMIN_BOOTSTRAP_CODE)
    has_admin = db.scalar(
        select(User.id).where(User.is_superuser.is_(True)).limit(1)
    ) is not None
    return {'available': configured and not has_admin, 'configured': configured, 'has_admin': has_admin}

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
        if user.password_hash is None or not verify_password(data.password, user.password_hash):
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
def register(data: UserRegistrationRequest, db: Session=Depends(get_db)):
    try:
        user = register_user(db, data)
    except EmailAlreadyRegisteredError as exc:
        if str(exc) == 'google':
            raise HTTPException(409, 'This email is already registered with Google. Please sign in with Google.')
        raise HTTPException(409, 'An account with this email already exists. Please log in.')
    return AuthResponse(user=UserResponse.model_validate(user), access_token=create_access_token(str(user.id)))

@router.post('/login', response_model=AuthResponse)
def login(data: UserLogin, db: Session=Depends(get_db)):
    try:
        user = authenticate_user(db, data.email, data.password)
    except GoogleOnlyAccountError:
        raise HTTPException(401, 'This account was created with Google. Please sign in with Google.')
    except AuthenticationError:
        # Use one response for an unknown email and a bad password to avoid
        # exposing which email addresses have accounts.
        raise HTTPException(401, 'Incorrect email or password. Please try again.')
    return AuthResponse(user=UserResponse.model_validate(user), access_token=create_access_token(str(user.id)))

@router.post('/google', response_model=AuthResponse)
def google_login(data: GoogleLoginRequest, db: Session=Depends(get_db)):
    """Verify a Google ID token and create or sign in to the matching account."""
    settings = get_settings()
    client_id = settings.GOOGLE_CLIENT_ID.strip()
    if not client_id:
        raise HTTPException(503, 'Google sign-in is not configured.')

    try:
        from google.auth.exceptions import GoogleAuthError
        from google.auth.transport.requests import Request as GoogleRequest
        from google.oauth2 import id_token

        identity = id_token.verify_oauth2_token(
            data.credential, GoogleRequest(), audience=client_id
        )
    except (ValueError, GoogleAuthError):
        raise HTTPException(401, 'Google could not verify this sign-in. Please try again.')

    email = str(identity.get('email', '')).strip().lower()
    full_name = str(identity.get('name') or email.split('@', 1)[0]).strip()[:150]
    if not identity.get('sub') or not email or not identity.get('email_verified'):
        raise HTTPException(401, 'Google did not provide a verified email address.')

    try:
        user = db.scalar(select(User).where(User.email == email).with_for_update())
        if user is not None:
            if not user.is_active:
                raise HTTPException(403, 'This account is disabled. Contact support for help.')
            # A verified matching email links Google to the existing account.
            user.is_verified = True
            db.commit()
            db.refresh(user)
        else:
            user = User(
                full_name=full_name,
                email=email,
                password_hash=None,
                is_verified=True,
            )
            db.add(user)
            try:
                db.commit()
                db.refresh(user)
            except IntegrityError as exc:
                # Handle a simultaneous signup, or an unapplied nullable-password migration.
                db.rollback()
                user = db.scalar(select(User).where(User.email == email))
                if user is None:
                    raise HTTPException(503, 'Google could not save this account. Apply the latest database migration with npm run migrate, then try again.') from exc
                if not user.is_active:
                    raise HTTPException(403, 'This account is disabled. Contact support for help.')
                user.is_verified = True
                db.commit()
                db.refresh(user)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(503, 'Google sign-in could not access the account database. Check the backend database connection and migrations, then try again.') from exc

    return AuthResponse(user=UserResponse.model_validate(user), access_token=create_access_token(str(user.id)))

@router.get('/me', response_model=UserResponse)
def me(user: User=Depends(current_user)):
    return user

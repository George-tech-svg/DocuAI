"""Register users, sign in, and return the authenticated user profile."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
import secrets
import logging
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.dependencies import current_user
from app.models.user import User
from app.models.entities import PrivacyConsent, AuditEvent
from app.schemas.auth import UserRegistrationRequest, UserLogin, GoogleLoginRequest, AdminBootstrapRequest, UserResponse, AuthResponse, AnswerLanguageUpdate
from app.services.auth_service import register_user, authenticate_user, EmailAlreadyRegisteredError, AuthenticationError, GoogleOnlyAccountError
from app.core.config import get_settings
from app.core.security import hash_password, verify_password
from app.services.security_controls import (CSRF_COOKIE, SESSION_COOKIE, clear_login_failures,
    enforce_rate_limit, generate_totp_secret, login_locked, record_login_failure,
    require_admin_totp, set_session_cookies, verify_totp)
from datetime import datetime, timezone
from urllib.parse import quote
router = APIRouter(prefix='/auth', tags=['Authentication'])
logger = logging.getLogger(__name__)

class AdminTotpEnable(BaseModel):
    secret: str = Field(min_length=24, max_length=64)
    code: str = Field(pattern=r'^\d{6}$')

class AdminTotpCode(BaseModel):
    code: str = Field(pattern=r'^\d{6}$')

def _client_key(request: Request) -> str:
    return request.client.host if request.client else 'unknown'

def _record_consents(db: Session, user: User):
    settings = get_settings()
    recorded = []
    for policy, version in (('terms', settings.TERMS_VERSION), ('privacy', settings.PRIVACY_POLICY_VERSION)):
        exists = db.scalar(select(PrivacyConsent.id).where(PrivacyConsent.user_id == user.id,
            PrivacyConsent.policy == policy, PrivacyConsent.version == version).limit(1))
        if not exists:
            db.add(PrivacyConsent(user_id=user.id, policy=policy, version=version,
                accepted_at=datetime.now(timezone.utc)))
            recorded.append((policy, version))
    if recorded:
        db.add(AuditEvent(organization_id=None, actor_user_id=user.id, action='registration_notices_accepted',
            resource_type='user', resource_id=str(user.id), details={'policies':[{'policy':p,'version':v} for p,v in recorded]}))

def _authenticated_response(user: User, response: Response, db: Session, accept_terms: bool = False):
    if accept_terms:
        _record_consents(db, user)
    if user.is_superuser:
        db.add(AuditEvent(organization_id=None, actor_user_id=user.id, action='admin_signed_in',
            resource_type='user', resource_id=str(user.id), details={}))
    db.commit()
    set_session_cookies(response, str(user.id))
    return AuthResponse(user=UserResponse.model_validate(user))

@router.get('/google/config')
def google_sign_in_config():
    """Return the public Google client ID so sign-in also works without a Vite build variable."""
    client_id = get_settings().GOOGLE_CLIENT_ID.strip()
    return {'enabled': bool(client_id), 'client_id': client_id or None}

@router.get('/csrf')
def csrf_token(response: Response, request: Request):
    import secrets
    token = request.cookies.get(CSRF_COOKIE) or secrets.token_urlsafe(32)
    response.set_cookie(CSRF_COOKIE, token, httponly=False, secure=get_settings().AUTH_COOKIE_SECURE,
        samesite='lax', path='/', max_age=60 * 60 * 24)
    return {'csrf_token': token}

@router.post('/logout')
def logout(response: Response):
    from app.services.security_controls import clear_session_cookies
    clear_session_cookies(response)
    return {'message': 'You have been signed out.'}

@router.get('/admin/bootstrap/status')
def admin_bootstrap_status(db: Session=Depends(get_db)):
    """Expose only whether the one-time setup is available, never its secret."""
    configured = bool(get_settings().ADMIN_BOOTSTRAP_CODE)
    has_admin = db.scalar(
        select(User.id).where(User.is_superuser.is_(True)).limit(1)
    ) is not None
    return {'available': configured and not has_admin, 'configured': configured, 'has_admin': has_admin}

@router.post('/admin/bootstrap', response_model=AuthResponse, response_model_exclude_none=True, status_code=201)
def bootstrap_admin(data: AdminBootstrapRequest, request: Request, response: Response, db: Session=Depends(get_db)):
    """Create or promote the first and only super administrator."""
    expected_code = get_settings().ADMIN_BOOTSTRAP_CODE
    if not expected_code:
        raise HTTPException(503, 'First-administrator setup is not configured. Set ADMIN_BOOTSTRAP_CODE in the backend environment.')
    if not secrets.compare_digest(data.setup_code, expected_code):
        raise HTTPException(403, 'The private setup code is incorrect. Check the ADMIN_BOOTSTRAP_CODE value in the Vercel backend environment.')
    enforce_rate_limit(db, 'admin-bootstrap-ip', _client_key(request), 5, 900)

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
    return _authenticated_response(user, response, db, accept_terms=True)

@router.post('/register', response_model=AuthResponse, response_model_exclude_none=True, status_code=201)
def register(data: UserRegistrationRequest, request: Request, response: Response, db: Session=Depends(get_db)):
    enforce_rate_limit(db, 'register-ip', _client_key(request), 5, 900)
    try:
        user = register_user(db, data)
    except EmailAlreadyRegisteredError as exc:
        if str(exc) == 'google':
            raise HTTPException(409, 'This email is already registered with Google. Please sign in with Google.')
        raise HTTPException(409, 'An account with this email already exists. Please log in.')
    _record_consents(db, user)
    db.commit()
    return AuthResponse(user=UserResponse.model_validate(user))

@router.post('/login', response_model=AuthResponse, response_model_exclude_none=True)
def login(data: UserLogin, request: Request, response: Response, db: Session=Depends(get_db)):
    normalized_email = str(data.email).lower()
    enforce_rate_limit(db, 'login-ip', _client_key(request), 20, 900)
    if login_locked(db, normalized_email):
        raise HTTPException(423, 'Too many sign-in attempts. This account is temporarily locked. Please try again in 15 minutes.')
    try:
        user = authenticate_user(db, normalized_email, data.password)
    except GoogleOnlyAccountError:
        record_login_failure(db, normalized_email)
        raise HTTPException(401, 'This account was created with Google. Please sign in with Google.')
    except AuthenticationError:
        record_login_failure(db, normalized_email)
        raise HTTPException(401, 'Incorrect email or password. Please try again.')
    if data.admin_login and not user.is_superuser:
        raise HTTPException(403, 'This account does not have administrator access. Sign in with an administrator account.')
    try:
        require_admin_totp(user, data.totp_code)
    except HTTPException:
        record_login_failure(db, normalized_email)
        raise
    clear_login_failures(db, normalized_email)
    return _authenticated_response(user, response, db)

@router.post('/google', response_model=AuthResponse, response_model_exclude_none=True)
def google_login(data: GoogleLoginRequest, request: Request, response: Response, db: Session=Depends(get_db)):
    """Verify a Google ID token and create or sign in to the matching account."""
    settings = get_settings()
    enforce_rate_limit(db, 'google-auth-ip', _client_key(request), 20, 900)
    if data.mode == 'register' and not data.accept_terms:
        raise HTTPException(400, 'Accept the Terms of Service and Privacy Notice before creating your account.')
    client_id = settings.GOOGLE_CLIENT_ID.strip()
    if not client_id:
        raise HTTPException(503, 'Google sign-in is not configured.')

    try:
        from google.auth.transport.requests import Request as GoogleRequest
        from google.oauth2 import id_token

        identity = id_token.verify_oauth2_token(
            data.credential, GoogleRequest(), audience=client_id
        )
    except ValueError:
        raise HTTPException(401, 'Google could not verify this sign-in. Please try again.')
    except Exception as exc:
        logger.exception('Unexpected failure while verifying a Google sign-in')
        raise HTTPException(503, 'Google sign-in could not reach the verification service. Please try again later.') from exc

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
        logger.exception('Database error while creating or linking a Google account')
        raise HTTPException(503, 'Google sign-in could not access the account database. Check the backend database connection and migrations, then try again.') from exc
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.exception('Unexpected failure while creating or linking a Google account')
        raise HTTPException(503, 'Google sign-in could not finish creating or linking this account. Please try again later.') from exc

    require_admin_totp(user, data.totp_code)
    return _authenticated_response(user, response, db, accept_terms=data.accept_terms)

@router.post('/admin-2fa/setup')
def admin_totp_setup(user: User=Depends(current_user)):
    if not user.is_superuser: raise HTTPException(403, 'Administrator access required.')
    secret = generate_totp_secret()
    issuer = quote('DocuMind AI')
    account = quote(user.email)
    return {'secret': secret, 'otpauth_uri': f'otpauth://totp/{issuer}:{account}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30'}

@router.get('/admin-2fa/status')
def admin_totp_status(user: User=Depends(current_user)):
    if not user.is_superuser: raise HTTPException(403, 'Administrator access required.')
    return {'enabled': bool(user.admin_totp_enabled)}

@router.post('/admin-2fa/enable')
def admin_totp_enable(data: AdminTotpEnable, user: User=Depends(current_user), db: Session=Depends(get_db)):
    if not user.is_superuser: raise HTTPException(403, 'Administrator access required.')
    if not verify_totp(data.secret, data.code): raise HTTPException(400, 'That authenticator code is not valid. Try again.')
    user.admin_totp_secret, user.admin_totp_enabled = data.secret, True
    db.add(AuditEvent(organization_id=None, actor_user_id=user.id, action='admin_2fa_enabled', resource_type='user', resource_id=str(user.id), details={}))
    db.commit()
    return {'enabled': True, 'message': 'Two-factor authentication is enabled for this administrator account.'}

@router.post('/admin-2fa/disable')
def admin_totp_disable(data: AdminTotpCode, user: User=Depends(current_user), db: Session=Depends(get_db)):
    if not user.is_superuser: raise HTTPException(403, 'Administrator access required.')
    if not user.admin_totp_enabled or not verify_totp(user.admin_totp_secret, data.code):
        raise HTTPException(400, 'That authenticator code is not valid. Two-factor authentication remains enabled.')
    user.admin_totp_secret, user.admin_totp_enabled = None, False
    db.add(AuditEvent(organization_id=None, actor_user_id=user.id, action='admin_2fa_disabled', resource_type='user', resource_id=str(user.id), details={}))
    db.commit()
    return {'enabled': False, 'message': 'Two-factor authentication is disabled.'}

@router.get('/me', response_model=UserResponse)
def me(user: User=Depends(current_user)):
    return user

@router.get('/preferences')
def get_preferences(user: User=Depends(current_user)):
    return {'answer_language': user.answer_language or 'auto'}

@router.put('/preferences')
def update_preferences(data: AnswerLanguageUpdate, user: User=Depends(current_user), db: Session=Depends(get_db)):
    user.answer_language = data.answer_language
    db.commit()
    return {'answer_language': user.answer_language}

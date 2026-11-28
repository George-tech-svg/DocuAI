"""Cookie session, CSRF, rate-limit, lockout, and admin TOTP helpers."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings

SESSION_COOKIE = 'documind_session'
CSRF_COOKIE = 'documind_csrf'
CSRF_HEADER = 'X-CSRF-Token'
LOGIN_FAILURE_LIMIT = 5
LOGIN_FAILURE_WINDOW = timedelta(minutes=15)
LOGIN_LOCK_DURATION = timedelta(minutes=15)


def _private_hash(scope: str, key: str) -> str:
    secret = get_settings().JWT_SECRET_KEY.encode()
    return hmac.new(secret, f'{scope}:{key}'.encode(), hashlib.sha256).hexdigest()


def enforce_rate_limit(db: Session, scope: str, key: str, limit: int, window_seconds: int) -> None:
    now = datetime.now(timezone.utc)
    window_bucket = int(now.timestamp()) // window_seconds
    bucket_hash = _private_hash(f'{scope}:{window_bucket}', key)
    row = db.execute(text("""
        INSERT INTO security_counters (bucket_hash, scope, count, window_started_at, updated_at)
        VALUES (:bucket_hash, :scope, 1, :now, :now)
        ON CONFLICT (bucket_hash) DO UPDATE
        SET count = security_counters.count + 1, updated_at = :now
        RETURNING count
    """), {'bucket_hash': bucket_hash, 'scope': scope, 'now': now}).first()
    db.commit()
    if row and row[0] > limit:
        raise HTTPException(429, 'Too many requests. Please wait and try again later.', headers={'Retry-After': str(window_seconds)})


def login_locked(db: Session, normalized_email: str) -> bool:
    key = _private_hash('login-failure', normalized_email.lower())
    result = db.execute(text('SELECT locked_until FROM security_counters WHERE bucket_hash = :key'), {'key': key}).first()
    return bool(result and result[0] and result[0] > datetime.now(timezone.utc))


def record_login_failure(db: Session, normalized_email: str) -> None:
    now = datetime.now(timezone.utc)
    key = _private_hash('login-failure', normalized_email.lower())
    row = db.execute(text("""
        INSERT INTO security_counters (bucket_hash, scope, count, window_started_at, updated_at)
        VALUES (:key, 'login-failure', 1, :now, :now)
        ON CONFLICT (bucket_hash) DO UPDATE SET
          count = CASE WHEN security_counters.window_started_at <= :reset_before THEN 1 ELSE security_counters.count + 1 END,
          window_started_at = CASE WHEN security_counters.window_started_at <= :reset_before THEN :now ELSE security_counters.window_started_at END,
          locked_until = CASE WHEN security_counters.window_started_at <= :reset_before THEN NULL ELSE security_counters.locked_until END,
          updated_at = :now
        RETURNING count
    """), {'key': key, 'now': now, 'reset_before': now - LOGIN_FAILURE_WINDOW}).first()
    if row and row[0] >= LOGIN_FAILURE_LIMIT:
        db.execute(text('UPDATE security_counters SET locked_until = :until WHERE bucket_hash = :key'),
                   {'until': now + LOGIN_LOCK_DURATION, 'key': key})
    db.commit()


def clear_login_failures(db: Session, normalized_email: str) -> None:
    key = _private_hash('login-failure', normalized_email.lower())
    db.execute(text('DELETE FROM security_counters WHERE bucket_hash = :key'), {'key': key})
    db.commit()


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode('ascii').rstrip('=')


def totp_code(secret: str, timestamp: int | None = None) -> str:
    key = base64.b32decode(secret + '=' * ((8 - len(secret) % 8) % 8), casefold=True)
    counter = int((timestamp if timestamp is not None else time.time()) // 30)
    digest = hmac.new(key, struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f'{binary % 1_000_000:06d}'


def verify_totp(secret: str | None, code: str | None, timestamp: int | None = None) -> bool:
    if not secret or not code or not code.isdigit() or len(code) != 6:
        return False
    now = time.time() if timestamp is None else timestamp
    return any(hmac.compare_digest(totp_code(secret, int(now + step * 30)), code) for step in (-1, 0, 1))


def require_admin_totp(user, code: str | None) -> None:
    if user.is_superuser and user.admin_totp_enabled and not verify_totp(user.admin_totp_secret, code):
        raise HTTPException(401, 'Enter a valid authenticator code to sign in as administrator.')


def set_session_cookies(response, user_id: str) -> None:
    from app.core.security import create_access_token
    secure = get_settings().AUTH_COOKIE_SECURE
    common = {'secure': secure, 'samesite': 'lax', 'path': '/', 'max_age': 60 * 60 * 24}
    response.set_cookie(SESSION_COOKIE, create_access_token(user_id), httponly=True, **common)
    response.set_cookie(CSRF_COOKIE, secrets.token_urlsafe(32), httponly=False, **common)


def clear_session_cookies(response) -> None:
    secure = get_settings().AUTH_COOKIE_SECURE
    response.delete_cookie(SESSION_COOKIE, path='/', secure=secure, httponly=True, samesite='lax')
    response.delete_cookie(CSRF_COOKIE, path='/', secure=secure, httponly=False, samesite='lax')

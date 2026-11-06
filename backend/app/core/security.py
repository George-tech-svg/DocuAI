"""Hash passwords and create or verify signed access tokens."""

from datetime import datetime, timedelta, timezone
import jwt
from pwdlib import PasswordHash
from app.core.config import get_settings
password_hash = PasswordHash.recommended()
ALGORITHM = 'HS256'

class TokenValidationError(Exception):
    pass

def hash_password(password: str) -> str:
    return password_hash.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)

def create_access_token(subject: str, minutes: int=1440) -> str:
    """Create a signed JWT for an authenticated user."""
    now = datetime.now(timezone.utc)
    return jwt.encode({'sub': str(subject), 'iat': now, 'exp': now + timedelta(minutes=minutes)}, get_settings().JWT_SECRET_KEY, algorithm=ALGORITHM)

def get_token_subject(token: str) -> str:
    """Read the user identifier from a verified JWT."""
    try:
        subject = jwt.decode(token, get_settings().JWT_SECRET_KEY, algorithms=[ALGORITHM], options={'require': ['sub', 'exp']})['sub']
        if not subject:
            raise ValueError('Missing subject')
        return subject
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise TokenValidationError('Invalid token') from exc

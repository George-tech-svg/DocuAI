import uuid
from types import SimpleNamespace

import pytest

from app.services.auth_service import (
    AuthenticationError,
    EmailAlreadyRegisteredError,
    authenticate_user,
    register_user,
)
from app.schemas.auth import UserRegister
from app.core.security import hash_password


class FakeSession:
    def __init__(self, existing=None):
        self.existing = existing
        self.added = None
        self.committed = False

    def scalar(self, statement):
        return self.existing

    def add(self, value):
        self.added = value

    def commit(self):
        self.committed = True

    def refresh(self, value):
        if value.is_active is None:
            value.is_active = True

    def rollback(self):
        pass


def test_register_normalizes_email_and_hashes_password():
    db = FakeSession()
    data = UserRegister(full_name='Example User', email='PERSON@EXAMPLE.COM', password='safe-pass-123')

    user = register_user(db, data)

    assert db.committed
    assert user.email == 'person@example.com'
    assert user.password_hash != 'safe-pass-123'
    assert authenticate_user(FakeSession(existing=user), 'PERSON@example.com', 'safe-pass-123') is user


def test_register_rejects_existing_email():
    db = FakeSession(existing=SimpleNamespace(email='person@example.com'))
    data = UserRegister(full_name='Example User', email='person@example.com', password='safe-pass-123')

    with pytest.raises(EmailAlreadyRegisteredError):
        register_user(db, data)


def test_login_rejects_wrong_password_or_inactive_user():
    db = FakeSession(existing=None)
    with pytest.raises(AuthenticationError):
        authenticate_user(db, 'missing@example.com', 'password')

    user = SimpleNamespace(
        id=uuid.uuid4(),
        email='person@example.com',
        password_hash=hash_password('password'),
        is_active=False,
    )
    with pytest.raises(AuthenticationError):
        authenticate_user(FakeSession(existing=user), 'person@example.com', 'password')

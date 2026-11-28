from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('sqlalchemy')

from app.services.security_controls import totp_code, verify_totp
from app.services import security_controls
from app.services import privacy_jobs


class Rows:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class ScopeDB:
    def __init__(self, folder, documents, conversations):
        self.responses = [folder, documents, conversations]

    def scalars(self, _statement):
        return Rows(self.responses.pop(0))


def test_personal_scope_includes_only_owner_private_conversations():
    owner, foreigner, folder_id = uuid4(), uuid4(), uuid4()
    folder = SimpleNamespace(id=folder_id, user_id=owner, organization_id=None)
    docs = [SimpleNamespace(id=uuid4())]
    own_private = SimpleNamespace(user_id=owner, visibility='private', knowledge_base_id=uuid4())
    shared = SimpleNamespace(user_id=owner, visibility='shared', knowledge_base_id=folder_id)
    other_private = SimpleNamespace(user_id=foreigner, visibility='private', knowledge_base_id=folder_id)
    db = ScopeDB([folder], docs, [own_private, shared, other_private])

    folders, documents, conversations = privacy_jobs._personal_scope(db, owner)

    assert folders == [folder]
    assert documents == docs
    assert conversations == [own_private]


def test_organization_scope_excludes_other_members_private_conversations():
    owner, member, org_id, folder_id = uuid4(), uuid4(), uuid4(), uuid4()
    folder = SimpleNamespace(id=folder_id, organization_id=org_id)
    docs = [SimpleNamespace(id=uuid4())]
    shared = SimpleNamespace(user_id=member, visibility='shared')
    owner_private = SimpleNamespace(user_id=owner, visibility='private')
    member_private = SimpleNamespace(user_id=member, visibility='private')
    db = ScopeDB([folder], docs, [shared, owner_private, member_private])

    folders, documents, conversations = privacy_jobs._organization_scope(db, org_id, owner)

    assert folders == [folder]
    assert documents == docs
    assert conversations == [shared, owner_private]


def test_organization_zip_excludes_other_members_private_chat(tmp_path):
    import json
    import zipfile
    owner, member, org_id, folder_id = uuid4(), uuid4(), uuid4(), uuid4()
    now = datetime.now(timezone.utc)
    folder = SimpleNamespace(id=folder_id, name='Shared folder', description='')
    shared = SimpleNamespace(id=uuid4(), user_id=member, visibility='shared', knowledge_base_id=folder_id,
        title='Shared chat', created_at=now)
    owner_private = SimpleNamespace(id=uuid4(), user_id=owner, visibility='private', knowledge_base_id=folder_id,
        title='Owner private', created_at=now)
    member_private = SimpleNamespace(id=uuid4(), user_id=member, visibility='private', knowledge_base_id=folder_id,
        title='Member private', created_at=now)
    message = SimpleNamespace(role='assistant', content='safe', created_at=now,
        sources_json='[]', metadata_json='{}', model_name='test')
    org = SimpleNamespace(id=org_id, name='Example Org', type='business')
    class ExportDB:
        def __init__(self): self.responses = [[folder], [], [shared, owner_private, member_private], [message], [message]]
        def get(self, model, _key): return org if model.__name__ == 'Organization' else None
        def scalars(self, _statement): return Rows(self.responses.pop(0))
    export = SimpleNamespace(organization_id=org_id, requested_by_user_id=owner)
    output = tmp_path / 'organization.zip'

    privacy_jobs.build_export_archive(ExportDB(), export, str(output))

    with zipfile.ZipFile(output) as archive:
        paths = set(archive.namelist())
        assert f'data/conversations/{shared.id}.json' in paths
        assert f'data/conversations/{owner_private.id}.json' in paths
        assert f'data/conversations/{member_private.id}.json' not in paths
        exported = json.loads(archive.read(f'data/conversations/{owner_private.id}.json'))
        assert exported[0]['content'] == 'safe'


def test_deletion_stays_retryable_if_cloud_storage_cleanup_fails(monkeypatch):
    owner, folder_id, deletion_id = uuid4(), uuid4(), uuid4()
    deletion = SimpleNamespace(id=deletion_id, target_type='account', target_id=owner,
        status='queued', error=None, completed_at=None)
    user = SimpleNamespace(id=owner)
    folder = SimpleNamespace(id=folder_id, user_id=owner, organization_id=None)
    document = SimpleNamespace(cloudinary_public_id='stored-asset', cloudinary_resource_type='raw')

    class DeletionDB:
        def __init__(self): self.deleted = False; self.scalar_calls = 0
        def get(self, model, key):
            if model.__name__ == 'DataDeletionRequest': return deletion
            if model.__name__ == 'User': return user
            return None
        def scalars(self, _statement):
            self.scalar_calls += 1
            return Rows([folder] if self.scalar_calls == 1 else [])
        def add(self, _row): pass
        def commit(self): pass
        def rollback(self): pass
        def delete(self, _row): self.deleted = True

    db = DeletionDB()
    calls = iter(([folder], [document], []))
    monkeypatch.setattr(privacy_jobs, '_personal_scope', lambda *_args: next(calls))
    def fail_delete(*_args, **_kwargs): raise RuntimeError('storage unavailable')
    monkeypatch.setattr(privacy_jobs, 'delete_file', fail_delete)

    with pytest.raises(RuntimeError, match='storage unavailable'):
        privacy_jobs.process_deletion(db, deletion_id)

    assert deletion.status == 'failed'
    assert 'storage unavailable' in deletion.error
    assert db.deleted is False


def test_totp_generates_and_verifies_six_digit_code():
    # RFC 6238 SHA-1 test secret; this implementation intentionally uses 6 digits.
    secret = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'
    code = totp_code(secret, timestamp=59)
    assert code == '287082'
    assert verify_totp(secret, code, timestamp=59)
    assert not verify_totp(secret, '000000', timestamp=59)


def test_rate_limit_rejects_request_over_limit(monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setattr(security_controls, 'get_settings', lambda: SimpleNamespace(JWT_SECRET_KEY='unit-test-secret'))
    class Result:
        def first(self): return (2,)
    class DB:
        def execute(self, *_args, **_kwargs): return Result()
        def commit(self): pass
    with pytest.raises(HTTPException) as exc:
        security_controls.enforce_rate_limit(DB(), 'chat', 'user-key', 1, 60)
    assert exc.value.status_code == 429

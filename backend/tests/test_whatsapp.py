import base64
import hashlib
import hmac
from datetime import datetime, timezone
from types import SimpleNamespace
from sqlalchemy import MetaData, Table, Column, Integer, String

from app.services.whatsapp_policy import command_kind, is_duplicate_message, linked_and_opted_in
from app.services.whatsapp_provider import verify_standard_webhook


def signed(secret: bytes, webhook_id: str, timestamp: int, body: bytes) -> str:
    signing = f'{webhook_id}.{timestamp}.'.encode() + body
    digest = base64.b64encode(hmac.new(secret, signing, hashlib.sha256).digest()).decode()
    return f'v1,{digest}'


def test_signature_accepts_valid_raw_body_and_rejects_tampering():
    key = b'a private signing key for tests'
    secret = 'whsec_' + base64.b64encode(key).decode()
    raw = b'{"type":"whatsapp.received", "data": {"id":"wam_test"}}'
    signature = signed(key, 'evt_test', 1_800_000_000, raw)
    assert verify_standard_webhook(secret, 'evt_test', '1800000000', raw, signature, now_seconds=1_800_000_000)
    assert not verify_standard_webhook(secret, 'evt_test', '1800000000', raw + b' ', signature, now_seconds=1_800_000_000)


def test_signature_rejects_stale_delivery_and_accepts_rotated_signature():
    active, previous = b'active key', b'old key'
    secret = 'whsec_' + base64.b64encode(active).decode()
    raw = b'{}'
    old_sig = signed(previous, 'evt', 1000, raw)
    new_sig = signed(active, 'evt', 1000, raw)
    assert not verify_standard_webhook(secret, 'evt', '1000', raw, old_sig, now_seconds=1301)
    assert verify_standard_webhook(secret, 'evt', '1000', raw, f'{old_sig} {new_sig}', now_seconds=1000)


def test_duplicate_webhook_or_provider_message_is_idempotent():
    class FakeMessages:
        table = Table('messages', MetaData(), Column('id', Integer), Column('webhook_id', String), Column('provider_message_id', String))
        id = table.c.id
        webhook_id = table.c.webhook_id
        provider_message_id = table.c.provider_message_id
    class FakeDb:
        def scalar(self, statement): return True
    assert is_duplicate_message(FakeDb(), 'evt_1', 'wam_1', FakeMessages)


def test_unlinked_or_opted_out_phone_cannot_retrieve_documents():
    assert not linked_and_opted_in(None)
    assert not linked_and_opted_in(SimpleNamespace(active=True, opted_in_at=None, opted_out_at=None))
    assert not linked_and_opted_in(SimpleNamespace(active=True, opted_in_at=datetime.now(timezone.utc), opted_out_at=datetime.now(timezone.utc)))
    assert linked_and_opted_in(SimpleNamespace(active=True, opted_in_at=datetime.now(timezone.utc), opted_out_at=None))


def test_stop_and_start_are_immediate_opt_in_commands():
    assert command_kind(' STOP ') == 'opt_out'
    assert command_kind('unsubscribe') == 'opt_out'
    assert command_kind('START') == 'opt_in'
    assert command_kind('hello') is None

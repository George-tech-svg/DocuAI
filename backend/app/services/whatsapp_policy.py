"""Small WhatsApp authorization and command rules, kept easy to test."""
def linked_and_opted_in(link) -> bool:
    return bool(link and link.active and link.opted_in_at and not link.opted_out_at)

def command_kind(text: str | None) -> str | None:
    value = (text or '').strip().lower()
    if value in {'stop', 'unsubscribe', 'quit'}: return 'opt_out'
    if value in {'start', 'unstop', 'subscribe'}: return 'opt_in'
    return None

def webhook_duplicate_keys(webhook_id: str, provider_message_id: str | None) -> tuple[str, ...]:
    """Stable dedupe identities for at-least-once delivery at either layer."""
    return tuple(value for value in (webhook_id, provider_message_id or '') if value)

def is_duplicate_message(db, webhook_id: str, provider_message_id: str | None, message_model) -> bool:
    from sqlalchemy import or_, select
    keys = webhook_duplicate_keys(webhook_id, provider_message_id)
    if not keys: return False
    conditions = []
    if webhook_id: conditions.append(message_model.webhook_id == webhook_id)
    if provider_message_id: conditions.append(message_model.provider_message_id == provider_message_id)
    return bool(db.scalar(select(message_model.id).where(or_(*conditions)).limit(1)))

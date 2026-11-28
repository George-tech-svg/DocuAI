"""Bird adapter for WhatsApp. Application code depends on this provider contract."""
from __future__ import annotations
import base64
import os
from typing import Protocol
from urllib.parse import urlparse
import httpx
from app.core.config import get_settings

class WhatsAppProvider(Protocol):
    def send_text(self, to: str, body: str, idempotency_key: str) -> dict: ...
    def send_template(self, to: str, slug: str, language: str, parameters: dict, idempotency_key: str) -> dict: ...
    def fetch_media(self, message_id: str, media_id: str, max_bytes: int) -> tuple[bytes, str]: ...
    def message_cost(self, provider_message_id: str) -> dict: ...

class BirdWhatsAppProvider:
    def __init__(self):
        self.settings = get_settings()
        self.api_key = self.settings.BIRD_API_KEY.strip()
        if not self.api_key:
            raise RuntimeError('WhatsApp is not configured. Set the Bird environment variables on the backend.')
        region = 'eu1' if self.api_key.startswith('bk_eu1_') else 'us1'
        self.base_url = f'https://{region}.platform.bird.com/v1'
        self.number_id = self.settings.BIRD_WHATSAPP_NUMBER_ID.strip()
        if not self.number_id or not self.settings.BIRD_WORKSPACE_ID.strip():
            raise RuntimeError('WhatsApp is not fully configured. Set BIRD_WORKSPACE_ID and BIRD_WHATSAPP_NUMBER_ID.')
        self._sender = None

    def _request(self, method: str, path: str, *, json=None, headers=None, follow_redirects=False):
        merged = {'Authorization': f'Bearer {self.api_key}', 'Accept': 'application/json'}
        if headers: merged.update(headers)
        with httpx.Client(timeout=httpx.Timeout(15, connect=5), follow_redirects=follow_redirects) as client:
            response = client.request(method, self.base_url + path, json=json, headers=merged)
        if response.status_code >= 400:
            raise RuntimeError('WhatsApp provider request failed. Check Bird credentials, sender setup, and server logs.')
        return response

    def sender_number(self) -> str:
        if self._sender: return self._sender
        response = self._request('GET', f'/whatsapp/numbers/{self.number_id}')
        data = response.json().get('data', response.json())
        number = data.get('phone_number') or data.get('phoneNumber')
        if not number:
            raise RuntimeError('Bird did not return the WhatsApp sender phone number for the configured number ID.')
        self._sender = number
        return number

    def send_text(self, to: str, body: str, idempotency_key: str) -> dict:
        response = self._request('POST', '/whatsapp/messages', json={
            'to': to, 'from': self.sender_number(), 'text': {'body': body}},
            headers={'Idempotency-Key': idempotency_key})
        return response.json() if response.content else {}

    def send_template(self, to: str, slug: str, language: str, parameters: dict, idempotency_key: str) -> dict:
        body = {'to': to, 'type': 'template', 'template': {'slug': slug, 'language': language, 'parameters': parameters}}
        if not slug.startswith('bird_'):
            body['from'] = self.sender_number()
        response = self._request('POST', '/whatsapp/messages', json=body, headers={'Idempotency-Key': idempotency_key})
        return response.json() if response.content else {}

    def fetch_media(self, message_id: str, media_id: str, max_bytes: int) -> tuple[bytes, str]:
        path = f'/whatsapp/messages/{message_id}/media/{media_id}'
        with httpx.Client(timeout=httpx.Timeout(20, connect=5), follow_redirects=False) as client:
            with client.stream('GET', self.base_url + path, headers={'Authorization': f'Bearer {self.api_key}'}) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get('location', '')
                    if urlparse(location).scheme != 'https': raise RuntimeError('Bird returned an unsafe media download link.')
                else:
                    location = ''
                if not location:
                    response.raise_for_status()
                    return self._read_bounded(response, max_bytes)
            # Bird's media redirect is a short-lived signed URL; do not forward
            # the Bird bearer token to its storage host.
            with client.stream('GET', location) as response:
                response.raise_for_status()
                content, _ = self._read_bounded(response, max_bytes)
                return content, response.headers.get('content-type', 'application/octet-stream')

    @staticmethod
    def _read_bounded(response, max_bytes: int) -> tuple[bytes, str]:
        length = response.headers.get('content-length')
        if length and int(length) > max_bytes:
            raise RuntimeError('The WhatsApp attachment is larger than the configured upload limit.')
        parts, total = [], 0
        for part in response.iter_bytes():
            total += len(part)
            if total > max_bytes:
                raise RuntimeError('The WhatsApp attachment is larger than the configured upload limit.')
            parts.append(part)
        return b''.join(parts), response.headers.get('content-type', 'application/octet-stream')

    def message_cost(self, provider_message_id: str) -> dict:
        return self._request('GET', f'/whatsapp/messages/{provider_message_id}').json()

def provider_from_env() -> BirdWhatsAppProvider:
    return BirdWhatsAppProvider()

def verify_standard_webhook(secret: str, webhook_id: str, timestamp: str, raw_body: bytes, signature: str, now_seconds: int | None = None) -> bool:
    """Verify Standard Webhooks v1 signature, including the five-minute replay bound."""
    import hashlib, hmac, time
    if not secret or not webhook_id or not timestamp or not signature: return False
    try:
        timestamp_int = int(timestamp)
        if abs((now_seconds if now_seconds is not None else int(time.time())) - timestamp_int) > 300: return False
        key_text = secret.removeprefix('whsec_')
        key = base64.b64decode(key_text, validate=True)
    except (ValueError, TypeError): return False
    signed = f'{webhook_id}.{timestamp}.'.encode() + raw_body
    digest = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    for item in signature.split():
        version, sep, value = item.partition(',')
        if sep and version == 'v1' and hmac.compare_digest(value, digest): return True
    return False

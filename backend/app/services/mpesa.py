"""Safaricom Daraja OAuth and customer-initiated monthly STK prompts."""
import base64
from datetime import datetime
from zoneinfo import ZoneInfo
import httpx
from fastapi import HTTPException
from app.core.config import get_settings

def mpesa_ready() -> bool:
    settings = get_settings()
    return all((settings.MPESA_CONSUMER_KEY, settings.MPESA_CONSUMER_SECRET,
                settings.MPESA_SHORTCODE, settings.MPESA_PASSKEY,
                settings.MPESA_CALLBACK_BASE_URL or settings.FRONTEND_ORIGIN))

def normalize_phone(value: str) -> str:
    digits = ''.join(character for character in value if character.isdigit())
    if digits.startswith('0') and len(digits) == 10:
        digits = '254' + digits[1:]
    elif digits.startswith('7') and len(digits) == 9:
        digits = '254' + digits
    if not digits.startswith('254') or len(digits) != 12 or digits[3] not in '17':
        raise HTTPException(422, 'Enter a valid Kenyan M-Pesa number, for example 0712345678.')
    return digits

def _base_url() -> str:
    return 'https://api.safaricom.co.ke' if get_settings().MPESA_ENVIRONMENT.lower() == 'production' else 'https://sandbox.safaricom.co.ke'

async def initiate_stk_push(*, phone_number: str, amount_kes: int, callback_url: str, account_reference: str) -> dict:
    settings = get_settings()
    if not mpesa_ready():
        raise HTTPException(503, 'M-Pesa payments are not configured yet.')
    phone = normalize_phone(phone_number)
    timestamp = datetime.now(ZoneInfo('Africa/Nairobi')).strftime('%Y%m%d%H%M%S')
    password = base64.b64encode(f'{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}'.encode()).decode()
    base = _base_url()
    async with httpx.AsyncClient(timeout=25) as client:
        try:
            auth = await client.get(
                f'{base}/oauth/v1/generate',
                params={'grant_type': 'client_credentials'},
                auth=(settings.MPESA_CONSUMER_KEY, settings.MPESA_CONSUMER_SECRET),
            )
            auth.raise_for_status()
            access_token = auth.json()['access_token']
            response = await client.post(
                f'{base}/mpesa/stkpush/v1/processrequest',
                headers={'Authorization': f'Bearer {access_token}'},
                json={
                    'BusinessShortCode': settings.MPESA_SHORTCODE,
                    'Password': password,
                    'Timestamp': timestamp,
                    'TransactionType': settings.MPESA_TRANSACTION_TYPE,
                    'Amount': amount_kes,
                    'PartyA': phone,
                    'PartyB': settings.MPESA_SHORTCODE,
                    'PhoneNumber': phone,
                    'CallBackURL': callback_url,
                    'AccountReference': account_reference[:12],
                    'TransactionDesc': 'DocuMind monthly subscription',
                },
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise HTTPException(502, 'Could not start the M-Pesa payment prompt. Please try again.') from exc
    if str(payload.get('ResponseCode')) != '0' or not payload.get('CheckoutRequestID'):
        raise HTTPException(502, payload.get('CustomerMessage') or payload.get('ResponseDescription') or 'M-Pesa did not accept the payment request.')
    return payload

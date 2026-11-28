"""Member plan listings, monthly M-Pesa checkout, and payment callbacks."""
from datetime import datetime, timedelta, timezone
import secrets
from zoneinfo import ZoneInfo
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.api.dependencies import current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import MpesaPayment, PaymentRecoveryRequest, Subscription, SubscriptionPlan, User
from app.models.entities import Organization, OrganizationMember
from app.services.permissions import can
from app.schemas.billing import BillingStatus, CheckoutRequest, CheckoutResponse, PaymentRecoveryCreate, PaymentRecoveryView, PaymentView, PlanResponse, SubscriptionView
from app.services.mpesa import initiate_stk_push, mpesa_ready, normalize_phone

router = APIRouter(tags=['Billing'])

def _subscription_view(db: Session, subscription: Subscription) -> SubscriptionView:
    plan = db.get(SubscriptionPlan, subscription.plan_id)
    return SubscriptionView(id=subscription.id, plan_id=subscription.plan_id,
        plan_name=plan.name if plan else 'Subscription plan', status=subscription.status,
        starts_at=subscription.starts_at, expires_at=subscription.expires_at,
        created_at=subscription.created_at)

@router.get('/billing/plans', response_model=list[PlanResponse])
def plans(db: Session=Depends(get_db)):
    return list(db.scalars(select(SubscriptionPlan).where(SubscriptionPlan.is_active.is_(True)).order_by(SubscriptionPlan.price_kes)).all())

@router.get('/billing/me', response_model=BillingStatus)
def my_billing(user: User=Depends(current_user), db: Session=Depends(get_db)):
    now = datetime.now(timezone.utc)
    expired = db.scalars(select(Subscription).where(
        Subscription.user_id == user.id, Subscription.organization_id.is_(None), Subscription.status == 'active',
        Subscription.expires_at <= now,
    )).all()
    for item in expired:
        item.status = 'expired'
    if expired:
        db.commit()
    subscription = db.scalar(select(Subscription).where(
        Subscription.user_id == user.id, Subscription.organization_id.is_(None), Subscription.status == 'active',
        Subscription.expires_at > now,
    ).order_by(Subscription.expires_at.desc()))
    if subscription is None:
        subscription = db.scalar(select(Subscription).where(
            Subscription.user_id == user.id, Subscription.organization_id.is_(None), Subscription.status == 'pending',
        ).order_by(Subscription.created_at.desc()))
    payments = db.scalars(select(MpesaPayment).where(MpesaPayment.user_id == user.id)
        .order_by(MpesaPayment.created_at.desc()).limit(20)).all()
    return BillingStatus(
        subscription=_subscription_view(db, subscription) if subscription else None,
        payments=[PaymentView.model_validate(payment) for payment in payments],
        mpesa_ready=mpesa_ready(),
    )

@router.get('/billing/payment-recovery', response_model=list[PaymentRecoveryView])
def my_payment_recovery_requests(user: User=Depends(current_user), db: Session=Depends(get_db)):
    return list(db.scalars(
        select(PaymentRecoveryRequest)
        .where(PaymentRecoveryRequest.user_id == user.id)
        .order_by(PaymentRecoveryRequest.created_at.desc())
        .limit(20)
    ).all())

@router.post('/billing/payment-recovery', response_model=PaymentRecoveryView, status_code=201)
def create_payment_recovery_request(data: PaymentRecoveryCreate, user: User=Depends(current_user), db: Session=Depends(get_db)):
    # Lock the member row to prevent two simultaneous requests both passing the pending check.
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    pending = db.scalar(select(PaymentRecoveryRequest.id).where(
        PaymentRecoveryRequest.user_id == user.id,
        PaymentRecoveryRequest.status == 'pending',
    ).limit(1))
    if pending:
        raise HTTPException(409, 'You already have a payment recovery request waiting for review.')
    paid_at = data.paid_at
    if paid_at.tzinfo is None:
        paid_at = paid_at.replace(tzinfo=ZoneInfo('Africa/Nairobi'))
    paid_at = paid_at.astimezone(timezone.utc)
    if paid_at > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise HTTPException(422, 'Payment time cannot be in the future.')
    payment_message = data.mpesa_message.strip()
    if len(payment_message) < 5:
        raise HTTPException(422, 'Paste the M-Pesa confirmation message or receipt so the administrator can review it.')
    request_record = PaymentRecoveryRequest(
        user_id=user.id,
        phone_number=normalize_phone(data.phone_number),
        paid_at=paid_at,
        mpesa_message=payment_message,
        status='pending',
    )
    db.add(request_record)
    db.commit()
    db.refresh(request_record)
    return request_record

@router.post('/billing/checkout', response_model=CheckoutResponse, status_code=202)
async def checkout(data: CheckoutRequest, user: User=Depends(current_user), db: Session=Depends(get_db)):
    if data.organization_id:
        organization = db.get(Organization, data.organization_id)
        if not organization or not can(user, 'manage_billing', organization, db):
            raise HTTPException(404, 'Organization not found or you cannot manage its billing.')
        current_seats = db.scalar(select(func.count(OrganizationMember.id)).where(OrganizationMember.organization_id == organization.id)) or 0
        if data.seat_limit is None or data.seat_limit < current_seats:
            raise HTTPException(422, f'Seat limit must cover all current members ({current_seats}).')
    elif data.seat_limit is not None:
        raise HTTPException(422, 'Seat limits are only used for organization subscriptions.')
    plan = db.scalar(select(SubscriptionPlan).where(
        SubscriptionPlan.id == data.plan_id, SubscriptionPlan.is_active.is_(True)))
    if not plan:
        raise HTTPException(404, 'Subscription plan not found')
    if not mpesa_ready():
        raise HTTPException(503, 'M-Pesa payments are not configured yet.')
    recent_pending = db.scalar(select(MpesaPayment.id).where(
        MpesaPayment.user_id == user.id, MpesaPayment.status == 'pending',
        MpesaPayment.created_at > datetime.now(timezone.utc) - timedelta(minutes=2),
    ).limit(1))
    if recent_pending:
        raise HTTPException(409, 'An M-Pesa prompt is already pending. Complete or wait for that request before trying again.')
    phone = normalize_phone(data.phone_number)
    subscription = Subscription(user_id=user.id, organization_id=data.organization_id, seat_limit=data.seat_limit, plan_id=plan.id, status='pending')
    db.add(subscription)
    db.flush()
    payment = MpesaPayment(
        user_id=user.id, subscription_id=subscription.id, amount_kes=plan.price_kes,
        phone_number=phone, status='pending', callback_token=secrets.token_urlsafe(32),
    )
    db.add(payment)
    db.commit()
    settings = get_settings()
    callback_base = (settings.MPESA_CALLBACK_BASE_URL or settings.FRONTEND_ORIGIN).rstrip('/')
    callback_url = f'{callback_base}{settings.API_V1_PREFIX}/billing/mpesa/callback/{payment.callback_token}'
    try:
        provider_response = await initiate_stk_push(
            phone_number=phone, amount_kes=payment.amount_kes,
            callback_url=callback_url, account_reference=f'DM{str(payment.id)[:8]}',
        )
    except HTTPException as exc:
        payment.status = 'failed'
        payment.result_description = str(exc.detail)[:255]
        subscription.status = 'failed'
        db.commit()
        raise
    payment.checkout_request_id = provider_response['CheckoutRequestID']
    payment.merchant_request_id = provider_response.get('MerchantRequestID')
    db.commit()
    return CheckoutResponse(payment_id=payment.id, subscription_id=subscription.id,
        status='pending', customer_message=provider_response.get('CustomerMessage', 'Check your phone and approve the M-Pesa prompt.'))

@router.post('/billing/mpesa/callback/{callback_token}')
async def mpesa_callback(callback_token: str, request: Request, db: Session=Depends(get_db)):
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(400, 'Invalid payment callback') from exc
    callback = payload.get('Body', {}).get('stkCallback', {})
    checkout_id = callback.get('CheckoutRequestID')
    payment = db.scalar(select(MpesaPayment).where(MpesaPayment.callback_token == callback_token).with_for_update())
    if payment is None or not checkout_id or checkout_id != payment.checkout_request_id:
        raise HTTPException(404, 'Payment request not found')
    # Callbacks may be retried; never extend access twice for the same payment.
    if payment.status == 'paid':
        return {'ResultCode': 0, 'ResultDesc': 'Already processed'}
    raw_result_code = callback.get('ResultCode')
    try:
        result_code = int(raw_result_code)
    except (TypeError, ValueError):
        result_code = None
    payment.result_code = result_code
    payment.result_description = str(callback.get('ResultDesc', ''))[:255]
    if result_code == 0:
        metadata = {item.get('Name'): item.get('Value') for item in callback.get('CallbackMetadata', {}).get('Item', [])}
        receipt = metadata.get('MpesaReceiptNumber')
        amount = metadata.get('Amount')
        if not receipt or amount is None or int(float(amount)) != payment.amount_kes:
            payment.status = 'review'
            payment.result_description = 'Payment callback requires reconciliation.'
            db.commit()
            return {'ResultCode': 0, 'ResultDesc': 'Accepted for reconciliation'}
        payment.status = 'paid'
        payment.mpesa_receipt = str(receipt)[:40]
        subscription = db.get(Subscription, payment.subscription_id)
        plan = db.get(SubscriptionPlan, subscription.plan_id) if subscription else None
        if subscription and plan:
            now = datetime.now(timezone.utc)
            current_query = select(Subscription).where(
                Subscription.status == 'active', Subscription.expires_at > now,
            )
            if subscription and subscription.organization_id:
                current_query = current_query.where(Subscription.organization_id == subscription.organization_id)
            else:
                current_query = current_query.where(Subscription.user_id == payment.user_id, Subscription.organization_id.is_(None))
            current = db.scalar(current_query.order_by(Subscription.expires_at.desc()).with_for_update())
            starts = current.expires_at if current else now
            subscription.status = 'active'
            subscription.starts_at = starts
            subscription.expires_at = starts + timedelta(days=plan.duration_days)
    else:
        payment.status = 'failed'
        subscription = db.get(Subscription, payment.subscription_id)
        if subscription:
            subscription.status = 'failed'
    db.commit()
    return {'ResultCode': 0, 'ResultDesc': 'Accepted'}

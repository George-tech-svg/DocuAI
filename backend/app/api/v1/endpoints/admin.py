"""Platform administration endpoints restricted to verified superusers."""
from datetime import datetime, timedelta, timezone
from importlib.util import find_spec
import json
import re
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session, aliased
from app.api.dependencies import admin_user
from app.db.session import get_db
from app.models.entities import AdminAuditLog, Conversation, Document, KnowledgeBase, Message, MpesaPayment, PaymentRecoveryRequest, Subscription, SubscriptionPlan, User
from app.schemas.billing import AdminActivity, AdminAuditEntry, AdminMember, AdminOverview, AdminPayment, AdminPaymentRecoveryView, AdminSubscription, AdminSubscriptionUpdate, MemberUpdate, PaymentRecoveryReview, PaymentRecoveryReviewResult, PlanCreate, PlanResponse, PlanUpdate, RecoveryMatch
from app.core.config import get_settings
from app.services.mpesa import mpesa_ready

router = APIRouter(prefix='/admin', tags=['Administration'], dependencies=[Depends(admin_user)])

def _recovery_matches(db: Session, recovery: PaymentRecoveryRequest) -> list[RecoveryMatch]:
    """Suggest recorded Daraja payments by receipt or a nearby phone/time match."""
    normalized_message = re.sub(r'[^A-Z0-9]', '', recovery.mpesa_message.upper())
    receipt_tokens = set(re.findall(r'(?<![A-Z0-9])[A-Z0-9]{8,12}(?![A-Z0-9])', recovery.mpesa_message.upper()))
    candidates: dict[UUID, tuple[MpesaPayment, User, SubscriptionPlan, str]] = {}
    if receipt_tokens:
        receipt_rows = db.execute(
            select(MpesaPayment, User, SubscriptionPlan)
            .join(User, User.id == MpesaPayment.user_id)
            .join(Subscription, Subscription.id == MpesaPayment.subscription_id)
            .join(SubscriptionPlan, SubscriptionPlan.id == Subscription.plan_id)
            .where(MpesaPayment.mpesa_receipt.in_(receipt_tokens))
            .limit(10)
        ).all()
        for payment, member, plan in receipt_rows:
            candidates[payment.id] = (payment, member, plan, 'M-Pesa receipt matches a recorded receipt')

    start = recovery.paid_at - timedelta(hours=24)
    end = recovery.paid_at + timedelta(hours=24)
    phone_rows = db.execute(
        select(MpesaPayment, User, SubscriptionPlan)
        .join(User, User.id == MpesaPayment.user_id)
        .join(Subscription, Subscription.id == MpesaPayment.subscription_id)
        .join(SubscriptionPlan, SubscriptionPlan.id == Subscription.plan_id)
        .where(
            MpesaPayment.phone_number == recovery.phone_number,
            or_(
                and_(MpesaPayment.created_at >= start, MpesaPayment.created_at <= end),
                and_(MpesaPayment.updated_at >= start, MpesaPayment.updated_at <= end),
            ),
        )
        .order_by(MpesaPayment.created_at.desc())
        .limit(20)
    ).all()
    for payment, member, plan in phone_rows:
        receipt = (payment.mpesa_receipt or '').upper()
        reason = ('M-Pesa receipt matches a recorded receipt'
                  if receipt and re.sub(r'[^A-Z0-9]', '', receipt) in normalized_message
                  else 'Phone number and payment time are within 24 hours')
        candidates[payment.id] = (payment, member, plan, reason)

    ordered = sorted(
        candidates.values(),
        key=lambda item: (
            0 if item[3].startswith('M-Pesa receipt') else 1,
            abs(((item[0].updated_at if item[0].status == 'paid' else item[0].created_at) - recovery.paid_at).total_seconds()),
        ),
    )[:10]
    return [RecoveryMatch(
        payment_id=payment.id,
        plan_id=plan.id,
        member_name=member.full_name,
        member_email=member.email,
        plan_name=plan.name,
        amount_kes=payment.amount_kes,
        phone_number=payment.phone_number,
        status=payment.status,
        mpesa_receipt=payment.mpesa_receipt,
        created_at=payment.updated_at if payment.status == 'paid' else payment.created_at,
        match_reason=reason,
    ) for payment, member, plan, reason in ordered]

@router.get('/overview', response_model=AdminOverview)
def overview(db: Session=Depends(get_db)):
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    settings = get_settings()
    try:
        google_verifier_available = find_spec('google.auth') is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        google_verifier_available = False
    return AdminOverview(
        members_total=db.scalar(select(func.count(User.id))) or 0,
        members_active=db.scalar(select(func.count(User.id)).where(User.is_active.is_(True))) or 0,
        documents_total=db.scalar(select(func.count(Document.id))) or 0,
        documents_ready=db.scalar(select(func.count(Document.id)).where(Document.status == 'ready')) or 0,
        documents_failed=db.scalar(select(func.count(Document.id)).where(Document.status == 'failed')) or 0,
        conversations_total=db.scalar(select(func.count(Conversation.id))) or 0,
        questions_total=db.scalar(select(func.count(Message.id)).where(Message.role == 'user')) or 0,
        questions_last_7_days=db.scalar(select(func.count(Message.id)).where(Message.role == 'user', Message.created_at >= week_ago)) or 0,
        subscriptions_active=db.scalar(select(func.count(Subscription.id)).where(Subscription.status == 'active', Subscription.starts_at <= now, Subscription.expires_at > now)) or 0,
        subscriptions_expiring=db.scalar(select(func.count(Subscription.id)).where(Subscription.status == 'active', Subscription.starts_at <= now, Subscription.expires_at > now, Subscription.expires_at <= now + timedelta(days=7))) or 0,
        payments_total=db.scalar(select(func.count(MpesaPayment.id))) or 0,
        payments_pending=db.scalar(select(func.count(MpesaPayment.id)).where(MpesaPayment.status.in_(['pending', 'review']))) or 0,
        revenue_kes=db.scalar(select(func.coalesce(func.sum(MpesaPayment.amount_kes), 0)).where(MpesaPayment.status == 'paid')) or 0,
        mpesa_ready=mpesa_ready(),
        google_ready=bool(settings.GOOGLE_CLIENT_ID.strip()) and google_verifier_available,
        ai_ready=bool(settings.DEEPSEEK_API_KEY.strip()),
        storage_ready=bool(settings.CLOUDINARY_CLOUD_NAME and settings.CLOUDINARY_API_KEY and settings.CLOUDINARY_API_SECRET),
    )

@router.get('/activity', response_model=list[AdminActivity])
def recent_activity(db: Session=Depends(get_db)):
    """Return recent event metadata without exposing document or chat contents."""
    events: list[AdminActivity] = []
    for user in db.scalars(select(User).order_by(User.created_at.desc()).limit(25)):
        events.append(AdminActivity(
            id=f'registration-{user.id}', kind='registration', member_name=user.full_name,
            member_email=user.email, summary='Registered an account', created_at=user.created_at,
        ))

    uploaded = db.execute(
        select(Document, User)
        .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
        .join(User, User.id == KnowledgeBase.user_id)
        .order_by(Document.created_at.desc()).limit(25)
    ).all()
    for document, user in uploaded:
        events.append(AdminActivity(
            id=f'document-{document.id}', kind='document', member_name=user.full_name,
            member_email=user.email,
            summary=f'Uploaded a document ({document.status})', created_at=document.created_at,
        ))

    questions = db.execute(
        select(Message, User)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .join(User, User.id == Conversation.user_id)
        .where(Message.role == 'user')
        .order_by(Message.created_at.desc()).limit(25)
    ).all()
    for message, user in questions:
        events.append(AdminActivity(
            id=f'question-{message.id}', kind='chat', member_name=user.full_name,
            member_email=user.email, summary='Asked a question in the chatbot',
            created_at=message.created_at,
        ))

    payments = db.execute(
        select(MpesaPayment, User)
        .join(User, User.id == MpesaPayment.user_id)
        .order_by(MpesaPayment.created_at.desc()).limit(25)
    ).all()
    for payment, user in payments:
        events.append(AdminActivity(
            id=f'payment-{payment.id}', kind='payment', member_name=user.full_name,
            member_email=user.email, summary=f'M-Pesa payment {payment.status}',
            created_at=payment.created_at,
        ))

    return sorted(events, key=lambda event: event.created_at, reverse=True)[:60]

@router.get('/payment-recovery', response_model=list[AdminPaymentRecoveryView])
def payment_recovery_requests(db: Session=Depends(get_db)):
    rows = db.execute(
        select(PaymentRecoveryRequest, User)
        .join(User, User.id == PaymentRecoveryRequest.user_id)
        .order_by(
            case((PaymentRecoveryRequest.status == 'pending', 0), else_=1),
            PaymentRecoveryRequest.created_at.desc(),
        )
        .limit(100)
    ).all()
    return [AdminPaymentRecoveryView(
        id=recovery.id,
        user_id=member.id,
        member_name=member.full_name,
        member_email=member.email,
        phone_number=recovery.phone_number,
        paid_at=recovery.paid_at,
        mpesa_message=recovery.mpesa_message,
        status=recovery.status,
        matched_payment_id=recovery.matched_payment_id,
        granted_subscription_id=recovery.granted_subscription_id,
        reviewed_by_user_id=recovery.reviewed_by_user_id,
        rejection_reason=recovery.rejection_reason,
        admin_note=recovery.admin_note,
        created_at=recovery.created_at,
        reviewed_at=recovery.reviewed_at,
        matches=_recovery_matches(db, recovery) if recovery.status == 'pending' else [],
    ) for recovery, member in rows]

@router.post('/payment-recovery/{request_id}/review', response_model=PaymentRecoveryReviewResult)
def review_payment_recovery(
    request_id: UUID,
    data: PaymentRecoveryReview,
    admin: User=Depends(admin_user),
    db: Session=Depends(get_db),
):
    recovery = db.scalar(
        select(PaymentRecoveryRequest)
        .where(PaymentRecoveryRequest.id == request_id)
        .with_for_update()
    )
    if recovery is None:
        raise HTTPException(404, 'Payment recovery request not found.')
    if recovery.status != 'pending':
        raise HTTPException(409, 'This payment recovery request has already been reviewed.')

    matches = _recovery_matches(db, recovery)
    matched_payment = None
    if data.matched_payment_id:
        if data.matched_payment_id not in {item.payment_id for item in matches}:
            raise HTTPException(422, 'Choose one of the suggested payment matches, or clear the match selection.')
        matched_payment = db.get(MpesaPayment, data.matched_payment_id)
    now = datetime.now(timezone.utc)
    member = db.get(User, recovery.user_id)
    if member is None:
        raise HTTPException(404, 'The member account for this request no longer exists.')

    granted_subscription = None
    audit_action: str
    if data.action == 'reject':
        reason = (data.reason or '').strip()
        if not reason:
            raise HTTPException(422, 'Enter a reason before rejecting this request.')
        recovery.status = 'rejected'
        recovery.rejection_reason = reason
        recovery.admin_note = None
        audit_action = 'payment_recovery_rejected'
        audit_reason = reason
    else:
        if not member.is_active:
            raise HTTPException(409, 'This member account is disabled. Enable it before granting access.')
        plan = db.get(SubscriptionPlan, data.plan_id) if data.plan_id else None
        if plan is None and matched_payment is not None:
            matched_subscription = db.get(Subscription, matched_payment.subscription_id)
            plan = db.get(SubscriptionPlan, matched_subscription.plan_id) if matched_subscription else None
        if plan is None:
            raise HTTPException(422, 'Choose a plan before granting access.')

        # A selected payment is evidence for the administrator; it never grants access by itself.
        # Only this explicit review action creates or extends an active subscription.
        if matched_payment is not None and matched_payment.user_id == member.id and matched_payment.status == 'paid':
            granted_subscription = db.scalar(
                select(Subscription).where(Subscription.id == matched_payment.subscription_id).with_for_update()
            )
        if granted_subscription is None:
            granted_subscription = db.scalar(
                select(Subscription)
                .where(
                    Subscription.user_id == member.id,
                    Subscription.status == 'active',
                    Subscription.expires_at > now,
                )
                .order_by(Subscription.expires_at.desc())
                .with_for_update()
            )

        if granted_subscription is None:
            granted_subscription = Subscription(
                user_id=member.id,
                plan_id=plan.id,
                status='active',
                starts_at=now,
                expires_at=now + timedelta(days=plan.duration_days),
            )
            db.add(granted_subscription)
            db.flush()
        else:
            existing_expiry = granted_subscription.expires_at
            if existing_expiry is not None and existing_expiry.tzinfo is None:
                existing_expiry = existing_expiry.replace(tzinfo=timezone.utc)
            grant_from = max(now, existing_expiry) if existing_expiry else now
            granted_subscription.plan_id = plan.id
            granted_subscription.status = 'active'
            granted_subscription.starts_at = granted_subscription.starts_at or now
            granted_subscription.expires_at = grant_from + timedelta(days=plan.duration_days)

        recovery.status = 'granted'
        recovery.matched_payment_id = matched_payment.id if matched_payment else None
        recovery.granted_subscription_id = granted_subscription.id
        recovery.reviewed_by_user_id = admin.id
        recovery.admin_note = (data.reason or '').strip() or None
        recovery.reviewed_at = now
        audit_action = 'payment_recovery_access_granted'
        audit_reason = recovery.admin_note or 'Administrator approved access after reviewing the payment recovery request.'
    if data.action == 'reject':
        recovery.matched_payment_id = matched_payment.id if matched_payment else None
        recovery.reviewed_by_user_id = admin.id
        recovery.reviewed_at = now

    audit = AdminAuditLog(
        admin_user_id=admin.id,
        payment_recovery_request_id=recovery.id,
        action=audit_action,
        reason=audit_reason,
        details=json.dumps({
            'member_id': str(member.id),
            'matched_payment_id': str(matched_payment.id) if matched_payment else None,
            'subscription_id': str(granted_subscription.id) if granted_subscription else None,
            'plan_id': str(granted_subscription.plan_id) if granted_subscription else None,
        }),
    )
    db.add(audit)
    db.commit()
    db.refresh(recovery)
    return PaymentRecoveryReviewResult(
        id=recovery.id,
        status=recovery.status,
        granted_subscription_id=recovery.granted_subscription_id,
        reviewed_at=recovery.reviewed_at,
    )

@router.get('/payment-recovery/audit', response_model=list[AdminAuditEntry])
def payment_recovery_audit(db: Session=Depends(get_db)):
    actor = aliased(User)
    rows = db.execute(
        select(AdminAuditLog, actor.email)
        .outerjoin(actor, actor.id == AdminAuditLog.admin_user_id)
        .where(AdminAuditLog.payment_recovery_request_id.is_not(None))
        .order_by(AdminAuditLog.created_at.desc())
        .limit(100)
    ).all()
    return [AdminAuditEntry(
        id=entry.id,
        admin_user_id=entry.admin_user_id,
        admin_email=email,
        payment_recovery_request_id=entry.payment_recovery_request_id,
        action=entry.action,
        reason=entry.reason,
        details=entry.details,
        created_at=entry.created_at,
    ) for entry, email in rows]

@router.get('/members', response_model=list[AdminMember])
def members(db: Session=Depends(get_db)):
    latest = select(Subscription.user_id.label('user_id'), func.max(Subscription.created_at).label('created_at')).group_by(Subscription.user_id).subquery()
    rows = db.execute(select(User, Subscription, SubscriptionPlan)
        .outerjoin(latest, latest.c.user_id == User.id)
        .outerjoin(Subscription, (Subscription.user_id == User.id) & (Subscription.created_at == latest.c.created_at))
        .outerjoin(SubscriptionPlan, SubscriptionPlan.id == Subscription.plan_id)
        .order_by(User.created_at.desc()).limit(1000)).all()
    return [AdminMember(id=user.id, full_name=user.full_name, email=user.email,
        is_active=user.is_active, is_superuser=user.is_superuser, created_at=user.created_at,
        current_plan=plan.name if plan else None, subscription_status=sub.status if sub else None,
        expires_at=sub.expires_at if sub else None) for user, sub, plan in rows]

@router.patch('/members/{user_id}', response_model=AdminMember)
def update_member(user_id: UUID, data: MemberUpdate, admin: User=Depends(admin_user), db: Session=Depends(get_db)):
    member = db.get(User, user_id)
    if member is None:
        raise HTTPException(404, 'Member not found')
    if member.id == admin.id and not data.is_active:
        raise HTTPException(400, 'You cannot deactivate your own administrator account.')
    member.is_active = data.is_active
    db.commit()
    db.refresh(member)
    latest = db.scalar(select(Subscription).where(Subscription.user_id == member.id).order_by(Subscription.created_at.desc()))
    plan = db.get(SubscriptionPlan, latest.plan_id) if latest else None
    return AdminMember(id=member.id, full_name=member.full_name, email=member.email,
        is_active=member.is_active, is_superuser=member.is_superuser, created_at=member.created_at,
        current_plan=plan.name if plan else None,
        subscription_status=latest.status if latest else None,
        expires_at=latest.expires_at if latest else None)

@router.get('/plans', response_model=list[PlanResponse])
def list_plans(db: Session=Depends(get_db)):
    return list(db.scalars(select(SubscriptionPlan).order_by(SubscriptionPlan.created_at.desc())).all())

@router.post('/plans', response_model=PlanResponse, status_code=201)
def create_plan(data: PlanCreate, db: Session=Depends(get_db)):
    plan = SubscriptionPlan(**data.model_dump())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan

@router.patch('/plans/{plan_id}', response_model=PlanResponse)
def update_plan(plan_id: UUID, data: PlanUpdate, db: Session=Depends(get_db)):
    plan = db.get(SubscriptionPlan, plan_id)
    if plan is None:
        raise HTTPException(404, 'Plan not found')
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(plan, key, value)
    db.commit()
    db.refresh(plan)
    return plan

@router.get('/subscriptions', response_model=list[AdminSubscription])
def list_subscriptions(db: Session=Depends(get_db)):
    rows = db.execute(select(Subscription, User, SubscriptionPlan)
        .join(User, User.id == Subscription.user_id)
        .join(SubscriptionPlan, SubscriptionPlan.id == Subscription.plan_id)
        .order_by(Subscription.created_at.desc()).limit(1000)).all()
    return [AdminSubscription(id=sub.id, user_id=user.id, full_name=user.full_name,
        email=user.email, plan_name=plan.name, price_kes=plan.price_kes,
        status=sub.status, starts_at=sub.starts_at, expires_at=sub.expires_at,
        created_at=sub.created_at) for sub, user, plan in rows]

@router.patch('/subscriptions/{subscription_id}')
def update_subscription(subscription_id: UUID, data: AdminSubscriptionUpdate, db: Session=Depends(get_db)):
    subscription = db.get(Subscription, subscription_id)
    if subscription is None:
        raise HTTPException(404, 'Subscription not found')
    subscription.status = data.status
    db.commit()
    return {'id': subscription.id, 'status': subscription.status}

@router.get('/payments', response_model=list[AdminPayment])
def list_payments(db: Session=Depends(get_db)):
    rows = db.execute(select(MpesaPayment, User)
        .join(User, User.id == MpesaPayment.user_id)
        .order_by(MpesaPayment.created_at.desc()).limit(1000)).all()
    return [AdminPayment(id=payment.id, user_id=user.id, full_name=user.full_name,
        email=user.email, amount_kes=payment.amount_kes, phone_number=payment.phone_number,
        status=payment.status, mpesa_receipt=payment.mpesa_receipt,
        result_description=payment.result_description, created_at=payment.created_at)
        for payment, user in rows]

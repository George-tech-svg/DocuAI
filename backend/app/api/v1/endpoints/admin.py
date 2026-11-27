"""Platform administration endpoints restricted to verified superusers."""
from datetime import datetime, timedelta, timezone
from importlib.util import find_spec
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.api.dependencies import admin_user
from app.db.session import get_db
from app.models.entities import Conversation, Document, KnowledgeBase, Message, MpesaPayment, Subscription, SubscriptionPlan, User
from app.schemas.billing import AdminActivity, AdminMember, AdminOverview, AdminPayment, AdminSubscription, AdminSubscriptionUpdate, MemberUpdate, PlanCreate, PlanResponse, PlanUpdate
from app.core.config import get_settings
from app.services.mpesa import mpesa_ready

router = APIRouter(prefix='/admin', tags=['Administration'], dependencies=[Depends(admin_user)])

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

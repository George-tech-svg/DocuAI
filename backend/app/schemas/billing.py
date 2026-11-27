"""Request and response models for plans and subscriptions."""
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

class PlanCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=1000)
    price_kes: int = Field(ge=1, le=1_000_000)
    duration_days: int = Field(default=30, ge=1, le=366)
    is_active: bool = True

class PlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    price_kes: int | None = Field(default=None, ge=1, le=1_000_000)
    duration_days: int | None = Field(default=None, ge=1, le=366)
    is_active: bool | None = None

class PlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    description: str
    price_kes: int
    duration_days: int
    is_active: bool
    created_at: datetime

class CheckoutRequest(BaseModel):
    plan_id: UUID
    phone_number: str = Field(min_length=9, max_length=16)

class CheckoutResponse(BaseModel):
    payment_id: UUID
    subscription_id: UUID
    status: str
    customer_message: str

class SubscriptionView(BaseModel):
    id: UUID
    plan_id: UUID
    plan_name: str
    status: str
    starts_at: datetime | None
    expires_at: datetime | None
    created_at: datetime

class PaymentView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    subscription_id: UUID
    amount_kes: int
    phone_number: str
    status: str
    mpesa_receipt: str | None
    result_description: str | None
    created_at: datetime

class BillingStatus(BaseModel):
    subscription: SubscriptionView | None
    payments: list[PaymentView]
    mpesa_ready: bool

class AdminOverview(BaseModel):
    members_total: int
    members_active: int
    documents_total: int
    documents_ready: int
    documents_failed: int
    conversations_total: int
    questions_total: int
    questions_last_7_days: int
    subscriptions_active: int
    subscriptions_expiring: int
    payments_total: int
    payments_pending: int
    revenue_kes: int
    mpesa_ready: bool
    google_ready: bool
    ai_ready: bool
    storage_ready: bool

class AdminActivity(BaseModel):
    id: str
    kind: str
    member_name: str
    member_email: str
    summary: str
    created_at: datetime

class AdminMember(BaseModel):
    id: UUID
    full_name: str
    email: str
    is_active: bool
    is_superuser: bool
    created_at: datetime
    current_plan: str | None = None
    subscription_status: str | None = None
    expires_at: datetime | None = None

class AdminSubscription(BaseModel):
    id: UUID
    user_id: UUID
    full_name: str
    email: str
    plan_name: str
    price_kes: int
    status: str
    starts_at: datetime | None
    expires_at: datetime | None
    created_at: datetime

class AdminPayment(BaseModel):
    id: UUID
    user_id: UUID
    full_name: str
    email: str
    amount_kes: int
    phone_number: str
    status: str
    mpesa_receipt: str | None
    result_description: str | None
    created_at: datetime

class AdminSubscriptionUpdate(BaseModel):
    status: str = Field(pattern="^cancelled$")

class MemberUpdate(BaseModel):
    is_active: bool

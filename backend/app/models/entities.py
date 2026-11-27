"""Database tables and relationships for the DocuMind AI application."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, ForeignKey, Boolean, Integer, BigInteger, DateTime, UniqueConstraint, false, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector
from app.db.base import Base

def uid():
    return uuid.uuid4()

def now():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = 'users'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    full_name: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # Google-only accounts have no password hash. A password account can also
    # be linked to Google by signing in with the same verified email.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    knowledge_bases = relationship('KnowledgeBase', back_populates='user', cascade='all, delete-orphan')
    conversations = relationship('Conversation', back_populates='user', cascade='all, delete-orphan')

class KnowledgeBase(Base):
    __tablename__ = 'knowledge_bases'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    user = relationship('User', back_populates='knowledge_bases')
    documents = relationship('Document', back_populates='knowledge_base', cascade='all, delete-orphan')
    conversations = relationship('Conversation', back_populates='knowledge_base')

class Document(Base):
    __tablename__ = 'documents'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('knowledge_bases.id', ondelete='CASCADE'), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(150))
    file_size_bytes: Mapped[int] = mapped_column(BigInteger)
    cloudinary_public_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cloudinary_resource_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    storage_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default='pending')
    progress_stage: Mapped[str] = mapped_column(String(20), default='uploading', server_default='uploading')
    ocr_used: Mapped[bool] = mapped_column(Boolean, default=False, server_default='false')
    ocr_confidence: Mapped[float | None] = mapped_column(nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    knowledge_base = relationship('KnowledgeBase', back_populates='documents')
    chunks = relationship('DocumentChunk', back_populates='document', cascade='all, delete-orphan')

class DocumentChunk(Base):
    __tablename__ = 'document_chunks'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(384))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    document = relationship('Document', back_populates='chunks')

class Conversation(Base):
    __tablename__ = 'conversations'
    __table_args__ = (Index('ix_conversations_user_pin_created', 'user_id', 'is_pinned', 'created_at'),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('knowledge_bases.id', ondelete='SET NULL'), nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('documents.id', ondelete='SET NULL'), nullable=True, index=True)
    scope_type: Mapped[str] = mapped_column(String(20), default='document', server_default='document')
    title: Mapped[str] = mapped_column(String(255), default='New chat')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Keep compatibility with existing Neon databases that still require this
    # legacy column, while allowing new schemas to create it with a DB default.
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    user = relationship('User', back_populates='conversations')
    knowledge_base = relationship('KnowledgeBase', back_populates='conversations')
    messages = relationship('Message', back_populates='conversation', cascade='all, delete-orphan')

class Message(Base):
    __tablename__ = 'messages'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('conversations.id', ondelete='CASCADE'), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    # Retain the position column required by the existing Neon schema.
    message_index: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    sources_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_error: Mapped[bool] = mapped_column(Boolean, default=False)
    conversation = relationship('Conversation', back_populates='messages')

class SubscriptionPlan(Base):
    __tablename__ = 'subscription_plans'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default='')
    price_kes: Mapped[int] = mapped_column(Integer)
    duration_days: Mapped[int] = mapped_column(Integer, default=30)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default='true')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

class Subscription(Base):
    __tablename__ = 'subscriptions'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('subscription_plans.id', ondelete='RESTRICT'), index=True)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

class MpesaPayment(Base):
    __tablename__ = 'mpesa_payments'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    subscription_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('subscriptions.id', ondelete='CASCADE'), index=True)
    amount_kes: Mapped[int] = mapped_column(Integer)
    phone_number: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default='pending', index=True)
    callback_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    checkout_request_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    merchant_request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mpesa_receipt: Mapped[str | None] = mapped_column(String(40), nullable=True, unique=True)
    result_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

class PaymentRecoveryRequest(Base):
    __tablename__ = 'payment_recovery_requests'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    phone_number: Mapped[str] = mapped_column(String(20))
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    mpesa_message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default='pending', index=True)
    matched_payment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('mpesa_payments.id', ondelete='SET NULL'), nullable=True)
    granted_subscription_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('subscriptions.id', ondelete='SET NULL'), nullable=True)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

class AdminAuditLog(Base):
    __tablename__ = 'admin_audit_logs'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    admin_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    payment_recovery_request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('payment_recovery_requests.id', ondelete='SET NULL'), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)

class Job(Base):
    __tablename__ = 'jobs'
    __table_args__ = (Index('ix_jobs_status_run_after', 'status', 'run_after'),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default='queued', server_default='queued', nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default='0', nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=4, server_default='4', nullable=False)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False, index=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now, nullable=False)

class DocumentEvent(Base):
    __tablename__ = 'document_events'
    __table_args__ = (Index('ix_document_events_user_due', 'user_id', 'due_at'),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    kind: Mapped[str] = mapped_column(String(30), default='other')
    title: Mapped[str] = mapped_column(String(300))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_excerpt: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column()
    status: Mapped[str] = mapped_column(String(20), default='suggested', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    document = relationship('Document')

class NotificationPreference(Base):
    __tablename__ = 'notification_preferences'
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    channels: Mapped[dict] = mapped_column(JSONB, default=lambda: {'email': True, 'in_app': True})
    lead_days: Mapped[list] = mapped_column(JSONB, default=lambda: [14, 7, 1])
    quiet_start: Mapped[str | None] = mapped_column(String(5), nullable=True)
    quiet_end: Mapped[str | None] = mapped_column(String(5), nullable=True)
    timezone: Mapped[str] = mapped_column(String(80), default='Africa/Nairobi', server_default='Africa/Nairobi')
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

class Reminder(Base):
    __tablename__ = 'reminders'
    __table_args__ = (UniqueConstraint('event_id', 'channel', 'remind_at', name='uq_reminder_event_channel_time'), Index('ix_reminders_status_time', 'status', 'remind_at'))
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('document_events.id', ondelete='CASCADE'), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    channel: Mapped[str] = mapped_column(String(20))
    remind_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default='scheduled', index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    event = relationship('DocumentEvent')

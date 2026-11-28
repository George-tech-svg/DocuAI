"""Database tables and relationships for the DocuMind AI application."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, ForeignKey, Boolean, Integer, BigInteger, DateTime, UniqueConstraint, false, Index, text, Numeric
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
    answer_language: Mapped[str] = mapped_column(String(8), default='auto', server_default='auto')
    admin_totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    admin_totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default='false')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    knowledge_bases = relationship('KnowledgeBase', back_populates='user', cascade='all, delete-orphan')
    conversations = relationship('Conversation', back_populates='user', cascade='all, delete-orphan')

class KnowledgeBase(Base):
    __tablename__ = 'knowledge_bases'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('organizations.id', ondelete='CASCADE'), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False, server_default='false')
    user = relationship('User', back_populates='knowledge_bases')
    documents = relationship('Document', back_populates='knowledge_base', cascade='all, delete-orphan')
    conversations = relationship('Conversation', back_populates='knowledge_base')

class Document(Base):
    __tablename__ = 'documents'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('knowledge_bases.id', ondelete='CASCADE'), index=True)
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
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
    uploaded_by_user = relationship('User', foreign_keys=[uploaded_by_user_id])
    chunks = relationship('DocumentChunk', back_populates='document', cascade='all, delete-orphan')

    @property
    def uploaded_by_name(self): return self.uploaded_by_user.full_name if self.uploaded_by_user else None
    @property
    def uploaded_by_email(self): return self.uploaded_by_user.email if self.uploaded_by_user else None

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
    library_collection_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('library_collections.id', ondelete='SET NULL'), nullable=True, index=True)
    scope_type: Mapped[str] = mapped_column(String(20), default='document', server_default='document')
    visibility: Mapped[str] = mapped_column(String(12), default='private', server_default='private')
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
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
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

class AnswerFeedback(Base):
    __tablename__ = 'answer_feedback'
    __table_args__ = (UniqueConstraint('user_id', 'assistant_message_id', name='uq_answer_feedback_user_message'), Index('ix_answer_feedback_status_created', 'status', 'created_at'))
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    assistant_message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('messages.id', ondelete='SET NULL'), nullable=True, index=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('conversations.id', ondelete='SET NULL'), nullable=True, index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    sources_json: Mapped[str] = mapped_column(Text, default='[]')
    model_version: Mapped[str] = mapped_column(String(100))
    rating: Mapped[str] = mapped_column(String(12), index=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default='new', server_default='new', index=True)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)

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
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('organizations.id', ondelete='CASCADE'), nullable=True, index=True)
    seat_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
    # Raw identifiers deliberately have no FK: deleting an account or recovery
    # request must not mutate or erase the append-only administrative trail.
    admin_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    payment_recovery_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
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

class LibraryCollection(Base):
    __tablename__ = 'library_collections'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default='')
    category: Mapped[str] = mapped_column(String(40), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    documents = relationship('LibraryDocument', back_populates='collection', cascade='all, delete-orphan')

class LibraryDocument(Base):
    __tablename__ = 'library_documents'
    __table_args__ = (
        UniqueConstraint('collection_id', 'short_name', 'content_hash', name='uq_library_doc_version_hash'),
        Index('ix_library_documents_current', 'collection_id', 'short_name', 'is_current'),
        Index('uq_library_one_current_version', 'collection_id', 'short_name', unique=True, postgresql_where=text('is_current = true')),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    collection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('library_collections.id', ondelete='CASCADE'), index=True)
    title: Mapped[str] = mapped_column(String(300))
    short_name: Mapped[str] = mapped_column(String(160), index=True)
    source_url: Mapped[str] = mapped_column(Text)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    storage_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    cloudinary_public_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cloudinary_resource_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    publisher: Mapped[str] = mapped_column(String(200))
    document_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version_label: Mapped[str] = mapped_column(String(120))
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, server_default='false', index=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default='queued', index=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_used: Mapped[bool] = mapped_column(Boolean, default=False, server_default='false')
    ocr_confidence: Mapped[float | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    collection = relationship('LibraryCollection', back_populates='documents')
    chunks = relationship('LibraryChunk', back_populates='document', cascade='all, delete-orphan')

class LibraryChunk(Base):
    __tablename__ = 'library_chunks'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    library_document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('library_documents.id', ondelete='CASCADE'), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_title: Mapped[str | None] = mapped_column(String(180), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(384))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    document = relationship('LibraryDocument', back_populates='chunks')

class LibraryUpdate(Base):
    __tablename__ = 'library_updates'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    collection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('library_collections.id', ondelete='CASCADE'), index=True)
    previous_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('library_documents.id', ondelete='SET NULL'), nullable=True)
    new_document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('library_documents.id', ondelete='CASCADE'), index=True)
    change_kind: Mapped[str] = mapped_column(String(20), default='added')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)

class DocumentEvent(Base):
    __tablename__ = 'document_events'
    __table_args__ = (Index('ix_document_events_user_due', 'user_id', 'due_at'),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('organizations.id', ondelete='SET NULL'), nullable=True, index=True)
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

class Organization(Base):
    __tablename__ = 'organizations'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(180))
    type: Mapped[str] = mapped_column(String(30))
    retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

class OrganizationMember(Base):
    __tablename__ = 'organization_members'
    __table_args__ = (UniqueConstraint('organization_id', 'user_id', name='uq_organization_member'), Index('ix_organization_members_user_role', 'user_id', 'role'))
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('organizations.id', ondelete='CASCADE'), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    role: Mapped[str] = mapped_column(String(20), default='member')
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class OrganizationInvite(Base):
    __tablename__ = 'organization_invites'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('organizations.id', ondelete='CASCADE'), index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(20), default='member')
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(20), default='pending', index=True)
    invited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class AuditEvent(Base):
    __tablename__ = 'audit_events'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(50), index=True)
    resource_type: Mapped[str] = mapped_column(String(50))
    resource_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)

class PrivacyConsent(Base):
    __tablename__ = 'privacy_consents'
    __table_args__ = (UniqueConstraint('user_id', 'policy', 'version', name='uq_privacy_consent_user_policy_version'),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    policy: Mapped[str] = mapped_column(String(30), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class SecurityCounter(Base):
    __tablename__ = 'security_counters'
    bucket_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    count: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

class DataExportRequest(Base):
    __tablename__ = 'data_export_requests'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default='queued', server_default='queued', index=True)
    storage_public_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class DataDeletionRequest(Base):
    __tablename__ = 'data_deletion_requests'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default='queued', server_default='queued', index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class WhatsAppLink(Base):
    __tablename__ = 'whatsapp_links'
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    phone_e164: Mapped[str] = mapped_column(String(20), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default='true')
    opted_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opted_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_source: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_knowledge_base_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('knowledge_bases.id', ondelete='SET NULL'), nullable=True)
    last_scope_type: Mapped[str] = mapped_column(String(20), default='folder', server_default='folder')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

class WhatsAppLinkChallenge(Base):
    __tablename__ = 'whatsapp_link_challenges'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    phone_e164: Mapped[str] = mapped_column(String(20), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class WhatsAppMessage(Base):
    __tablename__ = 'whatsapp_messages'
    __table_args__ = (UniqueConstraint('provider_message_id', name='uq_whatsapp_provider_message'), UniqueConstraint('idempotency_key', name='uq_whatsapp_idempotency'))
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    provider_message_id: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    webhook_id: Mapped[str | None] = mapped_column(String(180), nullable=True, unique=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    phone_e164: Mapped[str] = mapped_column(String(20), index=True)
    direction: Mapped[str] = mapped_column(String(10))
    kind: Mapped[str] = mapped_column(String(20), default='text')
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_id: Mapped[str | None] = mapped_column(String(180), nullable=True)
    media_mime_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    provider_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default='received')
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_offset: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    related_inbound_message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('whatsapp_messages.id', ondelete='SET NULL'), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(180), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)

class WhatsAppConsentEvent(Base):
    __tablename__ = 'whatsapp_consent_events'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    phone_e164: Mapped[str] = mapped_column(String(20), index=True)
    action: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(40))
    provider_message_id: Mapped[str | None] = mapped_column(String(180), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)

class MessageUsage(Base):
    __tablename__ = 'message_usage'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    whatsapp_message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('whatsapp_messages.id', ondelete='CASCADE'), unique=True, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    units: Mapped[int] = mapped_column(Integer, default=1, server_default='1')
    cost_amount: Mapped[object | None] = mapped_column(Numeric(12, 6), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    cost_status: Mapped[str] = mapped_column(String(20), default='pending', server_default='pending')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

class WhatsAppDocumentUpload(Base):
    __tablename__ = 'whatsapp_document_uploads'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), unique=True, index=True)
    inbound_message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('whatsapp_messages.id', ondelete='CASCADE'), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

"""Validate chat messages, sources, and conversation responses."""

from datetime import datetime
from uuid import UUID
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

class ChatRequest(BaseModel):
    scope_type: Literal['document', 'folder', 'library', 'folder_library']
    scope_id: UUID | None = None
    library_collection_id: UUID | None = None
    question: str = Field(min_length=2, max_length=3000)
    conversation_id: UUID | None = None
    visibility: Literal['private', 'shared'] = 'private'

class Source(BaseModel):
    document_id: UUID | None = None
    filename: str
    page_number: int | None = None
    excerpt: str
    source_type: Literal['document', 'library'] = 'document'
    version_label: str | None = None
    section_title: str | None = None
    source_url: str | None = None

class ChatResponse(BaseModel):
    answer: str
    conversation_id: UUID
    assistant_message_id: UUID
    sources: list[Source]
    answer_language: Literal['en', 'sw', 'mixed'] = 'en'
    confidence_score: float = 0
    confidence_label: Literal['Strong match', 'Partial match', 'Weak match'] = 'Weak match'
    search_query: str = ''

class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    user_id: UUID
    title: str
    knowledge_base_id: UUID | None
    document_id: UUID | None = None
    scope_type: Literal['document', 'folder', 'library', 'folder_library'] = 'document'
    library_collection_id: UUID | None = None
    visibility: Literal['private', 'shared'] = 'private'
    created_at: datetime
    is_archived: bool = False
    is_pinned: bool = False

class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    role: str
    content: str
    created_at: datetime
    sources: list[Source] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    actor_user_id: UUID | None = None
    actor_name: str | None = None
    actor_email: str | None = None
    feedback_status: Literal['up', 'down', 'report'] | None = None

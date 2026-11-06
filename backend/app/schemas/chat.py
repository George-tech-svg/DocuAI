"""Validate chat messages, sources, and conversation responses."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

class ChatRequest(BaseModel):
    knowledge_base_id: UUID
    question: str = Field(min_length=2, max_length=3000)
    conversation_id: UUID | None = None

class Source(BaseModel):
    document_id: UUID
    filename: str
    page_number: int | None = None
    excerpt: str

class ChatResponse(BaseModel):
    answer: str
    conversation_id: UUID
    sources: list[Source]

class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    knowledge_base_id: UUID | None
    created_at: datetime

class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    role: str
    content: str
    created_at: datetime

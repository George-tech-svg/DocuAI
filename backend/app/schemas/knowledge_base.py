"""Validate knowledge base requests and responses."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    organization_id: UUID | None = None
    is_sensitive: bool = False
    kind: str = Field(default='standard', pattern=r'^(standard|company_vault)$')

class KnowledgeBaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    is_archived: bool | None = None
    is_pinned: bool | None = None
    is_sensitive: bool | None = None
    kind: str | None = Field(default=None, pattern=r'^(standard|company_vault)$')

class KnowledgeBaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    is_archived: bool = False
    is_pinned: bool = False
    is_sensitive: bool = False
    kind: str = 'standard'
    organization_id: UUID | None = None
    user_id: UUID

class KnowledgeBaseListResponse(BaseModel):
    items: list[KnowledgeBaseResponse]
    total: int

"""Validate document metadata and upload responses."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    knowledge_base_id: UUID
    original_filename: str
    content_type: str
    file_size_bytes: int
    status: str
    page_count: int | None
    chunk_count: int
    processing_error: str | None
    created_at: datetime
    updated_at: datetime
    processed_at: datetime | None

class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int

class DocumentUploadResponse(BaseModel):
    document: DocumentResponse
    message: str

class DocumentStatusResponse(BaseModel):
    document_id: UUID
    status: str
    page_count: int | None = None
    chunk_count: int = Field(default=0, ge=0)
    processing_error: str | None = None
    processed_at: datetime | None = None

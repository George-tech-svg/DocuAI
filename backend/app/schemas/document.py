"""Validate document metadata and upload responses."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, computed_field

class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    knowledge_base_id: UUID
    original_filename: str
    content_type: str
    file_size_bytes: int
    status: str
    progress_stage: str = 'uploading'
    ocr_used: bool = False
    ocr_confidence: float | None = None
    page_count: int | None
    chunk_count: int
    processing_error: str | None
    created_at: datetime
    updated_at: datetime
    processed_at: datetime | None
    is_archived: bool = False
    is_pinned: bool = False

    @computed_field
    @property
    def low_ocr_confidence(self) -> bool:
        return self.ocr_used and (self.ocr_confidence is None or self.ocr_confidence < 60)

class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int

class DocumentUploadResponse(BaseModel):
    document: DocumentResponse
    message: str

class DocumentStatusResponse(BaseModel):
    document_id: UUID
    status: str
    progress_stage: str = 'uploading'
    page_count: int | None = None
    chunk_count: int = Field(default=0, ge=0)
    processing_error: str | None = None
    processed_at: datetime | None = None
    ocr_used: bool = False
    ocr_confidence: float | None = None
    low_ocr_confidence: bool = False

from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, field_validator

EventKind = Literal['deadline', 'expiry', 'hearing', 'payment_due', 'renewal', 'other']

class EventEdit(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    kind: EventKind = 'other'
    due_at: datetime

class SnoozeRequest(BaseModel):
    remind_at: datetime

class NotificationPreferencesUpdate(BaseModel):
    channels: dict[str, bool] = Field(default_factory=lambda: {'email': True, 'in_app': True})
    lead_days: list[int] = Field(default_factory=lambda: [14, 7, 1], max_length=10)
    quiet_start: str | None = None
    quiet_end: str | None = None
    timezone: str = 'Africa/Nairobi'

    @field_validator('lead_days')
    @classmethod
    def validate_lead_days(cls, values):
        if any(value < 0 or value > 365 for value in values):
            raise ValueError('Reminder lead times must be from 0 to 365 days.')
        return sorted(set(values), reverse=True)

class EventView(BaseModel):
    id: UUID
    document_id: UUID
    document_name: str
    kind: str
    title: str
    due_at: datetime
    source_page: int | None
    source_excerpt: str
    confidence: float
    status: str

class ReminderView(BaseModel):
    id: UUID
    event_id: UUID
    channel: str
    remind_at: datetime
    sent_at: datetime | None
    status: str
    error: str | None

class NotificationPreferencesView(NotificationPreferencesUpdate):
    pass

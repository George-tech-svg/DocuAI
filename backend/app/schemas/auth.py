"""Validate authentication requests and shape safe public responses."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

class UserRegister(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)

    @field_validator('password')
    @classmethod
    def strong_password(cls, v):
        if not (any((c.isupper() for c in v)) and any((c.islower() for c in v)) and any((c.isdigit() for c in v)) and any((not c.isalnum() for c in v))):
            raise ValueError('Password must contain uppercase, lowercase, digit and special character')
        return v

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    full_name: str
    email: EmailStr
    is_active: bool
    created_at: datetime

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'

class AuthResponse(BaseModel):
    user: UserResponse
    access_token: str
    token_type: str = 'bearer'

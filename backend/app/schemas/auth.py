"""Validate authentication requests and shape safe public responses."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field

class UserRegister(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    # Numeric-only passwords are valid; enforce only the advertised minimum.
    password: str = Field(min_length=4, max_length=128)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class AdminBootstrapRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    setup_code: str = Field(min_length=16, max_length=256)

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    full_name: str
    email: EmailStr
    is_active: bool
    is_superuser: bool = False
    created_at: datetime

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'

class AuthResponse(BaseModel):
    user: UserResponse
    access_token: str
    token_type: str = 'bearer'

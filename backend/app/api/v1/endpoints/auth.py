"""Register users, sign in, and return the authenticated user profile."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.dependencies import current_user
from app.models.user import User
from app.schemas.auth import UserRegister, UserLogin, UserResponse, AuthResponse
from app.services.auth_service import register_user, authenticate_user, EmailAlreadyRegisteredError, AuthenticationError
from app.core.security import create_access_token
router = APIRouter(prefix='/auth', tags=['Authentication'])

@router.post('/register', response_model=AuthResponse, status_code=201)
def register(data: UserRegister, db: Session=Depends(get_db)):
    try:
        user = register_user(db, data)
    except EmailAlreadyRegisteredError:
        raise HTTPException(409, 'Email already registered')
    return AuthResponse(user=UserResponse.model_validate(user), access_token=create_access_token(str(user.id)))

@router.post('/login', response_model=AuthResponse)
def login(data: UserLogin, db: Session=Depends(get_db)):
    try:
        user = authenticate_user(db, data.email, data.password)
    except AuthenticationError:
        raise HTTPException(401, 'Invalid credentials')
    return AuthResponse(user=UserResponse.model_validate(user), access_token=create_access_token(str(user.id)))

@router.get('/me', response_model=UserResponse)
def me(user: User=Depends(current_user)):
    return user

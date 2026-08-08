from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.auth.service import AuthService
from app.database.session import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
):
    service = AuthService(UserRepository(db), db)

    try:
        return service.register(payload)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
):
    service = AuthService(UserRepository(db), db)

    try:
        result = service.login(payload)

        return {
            "access_token": result["access_token"],
            "token_type": "bearer",
        }

    except ValueError as e:
        raise HTTPException(401, str(e)) from e


@router.get(
    "/me",
    response_model=UserResponse,
)
def current_user(
    current_user: User = Depends(get_current_user),
):
    return current_user

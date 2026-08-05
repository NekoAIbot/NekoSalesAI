from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config.security import create_access_token, verify_password
from app.dependencies.database import get_db
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserLogin
from app.services.user_service import UserService

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    payload: UserCreate,
    db: Session = Depends(get_db),
):
    service = UserService(db)

    try:
        user = service.register(payload)

        return {
            "message": "User created successfully.",
            "user_id": user.id,
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )


@router.post("/login")
def login(
    payload: UserLogin,
    db: Session = Depends(get_db),
):
    repository = UserRepository(db)

    user = repository.get_by_email(payload.email)

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password.",
        )

    if not verify_password(
        payload.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password.",
        )

    token = create_access_token(
        {
            "sub": str(user.id),
            "email": user.email,
        }
    )

    return {
        "access_token": token,
        "token_type": "bearer",
    }

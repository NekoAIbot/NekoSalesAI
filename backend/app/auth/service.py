from app.auth.schemas import (
    LoginRequest,
    RegisterRequest,
)
from app.auth.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.repositories.user_repository import UserRepository


class AuthService:
    def __init__(self, repository: UserRepository):
        self.repository = repository

    def register(self, data: RegisterRequest):
        if self.repository.email_exists(data.email):
            raise ValueError("Email already exists.")

        user = self.repository.create(
            full_name=data.full_name,
            email=data.email,
            password_hash=hash_password(data.password),
        )

        return user

    def login(self, data: LoginRequest):
        user = self.repository.get_by_email(data.email)

        if not user:
            raise ValueError("Invalid email or password.")

        if not verify_password(
            data.password,
            user.password_hash,
        ):
            raise ValueError("Invalid email or password.")

        token = create_access_token(
            subject=str(user.id)
        )

        return {
            "access_token": token,
            "token_type": "bearer",
            "user": user,
        }

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate


class UserService:

    def __init__(self, db: Session):
        self.repo = UserRepository(db)

    def register(self, data: UserCreate):

        if self.repo.get_by_email(data.email):
            raise ValueError("Email already exists.")

        user = User(
            full_name=data.full_name,
            email=data.email,
            password_hash=hash_password(data.password),
        )

        return self.repo.create(user)

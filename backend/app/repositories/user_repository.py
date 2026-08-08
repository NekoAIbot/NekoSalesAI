
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        full_name: str,
        email: str,
        password_hash: str,
        is_admin: bool = False,
        organization_id: int | None = None,
    ) -> User:
        user = User(
            full_name=full_name,
            email=email.lower(),
            password_hash=password_hash,
            is_active=True,
            is_admin=is_admin,
            organization_id=organization_id,
        )

        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

        return user

    def get_by_email(
        self,
        email: str,
    ) -> User | None:
        statement = select(User).where(
            User.email == email.lower()
        )

        return self.db.scalar(statement)

    def get_by_id(
        self,
        user_id: int,
    ) -> User | None:
        statement = select(User).where(
            User.id == user_id
        )

        return self.db.scalar(statement)

    def email_exists(
        self,
        email: str,
    ) -> bool:
        return self.get_by_email(email) is not None

    def list_users(
        self,
        skip: int = 0,
        limit: int = 100,
    ):
        statement = (
            select(User)
            .offset(skip)
            .limit(limit)
        )

        return list(self.db.scalars(statement).all())

    def delete(
        self,
        user: User,
    ) -> None:
        self.db.delete(user)
        self.db.commit()

    def update(self) -> None:
        self.db.commit()

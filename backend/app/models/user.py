from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel


class User(BaseModel):
    __tablename__ = "users"

    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id"),
        nullable=True,
    )

    full_name: Mapped[str] = mapped_column(String(120))

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255)
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )

    is_admin: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    organization = relationship(
        "Organization",
        backref="users",
    )

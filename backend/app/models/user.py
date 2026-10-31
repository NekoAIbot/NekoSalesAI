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

    email_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    phone_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # A password issued out-of-band (telegram /connect). The owner signs in
    # once with it and is forced to replace it immediately.
    password_is_temp: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    totp_secret: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    totp_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    recovery_codes: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
    )

    organization = relationship(
        "Organization",
        backref="users",
    )

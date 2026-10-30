"""Organization-scoped owner memory for Mira."""
from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import BaseModel


class MiraMemory(BaseModel):
    __tablename__ = "mira_memories"

    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(160), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="owner")

    __table_args__ = (
        UniqueConstraint("organization_id", "key", name="uq_mira_memory_org_key"),
    )

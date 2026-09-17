"""Configuration model for a provisioned workspace.

Persists what the buyer selected in the builder (channels, volume, integrations,
languages, workflow steps) so provisioning, the agent config, and follow-ups all
read the same agreed configuration rather than re-deriving it from a quote row
that may be hard to interpret.

One configuration per workspace profile. It is created by the builder/checkout
flow and read by provisioning and the agent.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel

CHANNEL_EMAIL = "email"
CHANNEL_TELEGRAM = "telegram"
CHANNEL_WHATSAPP = "whatsapp"
CHANNEL_WEB = "web"

ALL_CHANNELS = (CHANNEL_EMAIL, CHANNEL_TELEGRAM, CHANNEL_WHATSAPP, CHANNEL_WEB)

CHANNEL_LABELS = {
    CHANNEL_EMAIL: "Email",
    CHANNEL_TELEGRAM: "Telegram",
    CHANNEL_WHATSAPP: "WhatsApp",
    CHANNEL_WEB: "Web widget",
}


class WorkspaceConfiguration(BaseModel):
    """What a buyer asked for and what they are entitled to.

    Stored per workspace profile so provisioning, the agent config, and the
    dashboard all read one agreed truth instead of re-interpreting a quote's
    requirement JSON each time.
    """

    __tablename__ = "workspace_configurations"

    profile_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspace_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Channels the buyer selected. Web widget is always included.
    channels: Mapped[str] = mapped_column(
        String(120), nullable=False, default=CHANNEL_WEB
    )

    # Monthly conversation volume the buyer asked for, or None if not specified.
    monthly_conversations: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    # Number of external systems the agent must talk to.
    integrations: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    # Languages beyond the built-in one.
    languages: Mapped[str] = mapped_column(
        String(200), nullable=False, default=""
    )

    # Custom workflow steps the buyer asked for.
    workflow_steps: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    # When this configuration was agreed. Becomes the buyer's "this is what I
    # configured" record.
    agreed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    profile: Mapped["WorkspaceProfile"] = relationship()

    @property
    def channel_list(self) -> tuple[str, ...]:
        raw = (self.channels or "").split(",")
        chosen = [c.strip().lower() for c in raw if c.strip()]
        kept = [c for c in ALL_CHANNELS if c in chosen]
        if CHANNEL_WEB not in kept:
            kept.insert(0, CHANNEL_WEB)
        return tuple(kept)

    @property
    def language_list(self) -> tuple[str, ...]:
        raw = (self.languages or "").split(",")
        return tuple(l.strip() for l in raw if l.strip())

    def to_requirement_channels(self) -> tuple[str, ...]:
        """Channels in the shape the pricing engine expects."""
        return self.channel_list

    def to_requirement(self, product_type: str) -> dict:
        """A dict shaped like the pricing Requirement fields, for re-pricing."""
        from app.pricing.complexity import Requirement

        return Requirement(
            product_type=product_type,
            products=(product_type,),
            channels=self.to_requirement_channels(),
            integrations=tuple(
                f"system {n + 1}" for n in range(self.integrations)
            ),
            languages=self.language_list,
            monthly_conversations=self.monthly_conversations or 0,
            workflow_steps=self.workflow_steps,
        )

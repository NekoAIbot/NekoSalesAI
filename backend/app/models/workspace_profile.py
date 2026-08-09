"""Provisioned workspaces.

What a customer gets when they pay is not a copy of the software. It is a row
here: a configuration profile that the one shared engine reads at request time
to behave like their sales rep instead of ours. Their agent's name, tone,
greeting and the plans it is allowed to quote all live in this table.

That is the whole architecture, and it is deliberate. Forking a codebase per
customer means every bug is fixed N times and no two customers are ever
running the same thing. One engine plus a config row means a fix ships once.

Provisioning steps are recorded individually rather than as a single
in_progress flag, because the customer is watching this happen. A screen that
can say "workspace created, key issued, widget ready" is telling the truth
about where it is; a spinner is only saying that something, somewhere, is
still going.
"""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel

PROVISION_PENDING = "pending"
PROVISION_READY = "ready"
PROVISION_FAILED = "failed"

PROVISION_STATUSES = (PROVISION_PENDING, PROVISION_READY, PROVISION_FAILED)

# The steps, in the order they run. The UI renders this sequence, so it is
# defined here rather than duplicated in a template.
STEP_WORKSPACE = "workspace"
STEP_ADMIN = "admin_user"
STEP_API_KEY = "api_key"
STEP_WIDGET = "widget"

PROVISION_STEPS = (STEP_WORKSPACE, STEP_ADMIN, STEP_API_KEY, STEP_WIDGET)

STEP_LABELS = {
    STEP_WORKSPACE: "Creating workspace",
    STEP_ADMIN: "Setting up your login",
    STEP_API_KEY: "Issuing API key",
    STEP_WIDGET: "Preparing your widget",
}


class WorkspaceProfile(BaseModel):
    """One customer's configuration of the shared engine."""

    __tablename__ = "workspace_profiles"

    # The customer's own organization — created during provisioning, distinct
    # from the storefront org that sold to them.
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    order_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    plan_code: Mapped[str] = mapped_column(String(50), nullable=False)

    status: Mapped[str] = mapped_column(
        String(20),
        default=PROVISION_PENDING,
        nullable=False,
        index=True,
    )

    # How their agent introduces itself. Defaults are filled in at
    # provisioning time so the widget works before they touch the form.
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    company_name: Mapped[str] = mapped_column(String(150), nullable=False)
    greeting: Mapped[str] = mapped_column(Text, nullable=False)
    tone: Mapped[str] = mapped_column(String(40), nullable=False, default="professional")
    accent_color: Mapped[str] = mapped_column(String(20), nullable=False, default="#1c5d43")

    # Only ever a hash. If this table leaks, it must not hand over working
    # keys — the prefix is stored separately so the UI can show which key is
    # which without being able to reconstruct one.
    api_key_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    api_key_prefix: Mapped[str | None] = mapped_column(String(16), nullable=True)
    api_key_issued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Public identifier embedded in the customer's website. Not a secret: it
    # ends up in page source, so it authorises starting a conversation and
    # nothing else.
    widget_token: Mapped[str | None] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=True,
    )

    # Step-by-step progress, as JSON: {"workspace": "2026-01-01T...", ...}
    # Written as each step completes so the status endpoint reports real
    # progress rather than an estimate.
    steps_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # The customer's product config — plans, capabilities, knowledge, identity.
    # Stage A: assembled during provisioning from the purchase (plan_code), a
    # requirements-intake form (capabilities, knowledge), and sensible defaults
    # (company_name, tagline). Stage C replaces the fixed plan_code with
    # dynamic complexity-based pricing built into the config.
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    ready_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    organization: Mapped["Organization"] = relationship()  # noqa: F821

    @property
    def is_ready(self) -> bool:
        return self.status == PROVISION_READY

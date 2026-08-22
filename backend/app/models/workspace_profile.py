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
from app.products.config import ROLE_SALES_AGENT

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

# How a follow-up can reach a customer.
#
# Email is the default and cannot be turned off. It is the address the purchase
# was made with, so it is the one destination we always hold — and a customer who
# disabled every channel would have silently opted out of their own onboarding.
CHANNEL_EMAIL = "email"
CHANNEL_TELEGRAM = "telegram"
CHANNEL_WHATSAPP = "whatsapp"

FOLLOW_UP_CHANNELS = (CHANNEL_EMAIL, CHANNEL_TELEGRAM, CHANNEL_WHATSAPP)

CHANNEL_LABELS = {
    CHANNEL_EMAIL: "Email",
    CHANNEL_TELEGRAM: "Telegram",
    CHANNEL_WHATSAPP: "WhatsApp",
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

    # Which product they bought, and therefore what their agent is permitted
    # to do. Deliberately a column rather than a field inside config_json:
    # config_json is customer-editable through requirements intake, so a role
    # stored there could be edited, and editing it upward would turn a support
    # agent into one that can quote prices and take money. Set once at
    # provisioning from the purchase; intake cannot reach it.
    role: Mapped[str] = mapped_column(
        String(40), nullable=False, default=ROLE_SALES_AGENT
    )

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

    # Indexed because app.auth.api_key narrows by it on every authenticated
    # request before comparing the hash. Not unique: it is a slice of a generated
    # key, so a collision is possible and harmless — the hash still decides.
    api_key_prefix: Mapped[str | None] = mapped_column(
        String(16),
        index=True,
        nullable=True,
    )
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

    # Where post-sale follow-ups should go, as a comma-separated list of channel
    # codes. Email is the default and is always available, because it is the
    # address the purchase was made with — the others need a destination the
    # customer has to supply, so a stored preference naming one is not proof it
    # can be reached. FollowUpDispatcher checks both.
    follow_up_channels: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        default=CHANNEL_EMAIL,
        server_default=CHANNEL_EMAIL,
    )

    # Destinations for the optional channels. A numeric chat id for Telegram,
    # an E.164 number for WhatsApp. Null means the channel cannot be used even
    # if it is listed above.
    telegram_chat_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    whatsapp_number: Mapped[str | None] = mapped_column(String(32), nullable=True)

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

    @property
    def chosen_channels(self) -> tuple[str, ...]:
        """The channels the customer asked for, cleaned up.

        Email is added back if it is missing and unknown codes are dropped, so a
        stale or hand-edited row cannot leave a workspace unreachable or point at
        a channel this release does not implement.
        """
        raw = (self.follow_up_channels or "").split(",")
        chosen = [code.strip().lower() for code in raw if code.strip()]

        kept = [code for code in FOLLOW_UP_CHANNELS if code in chosen]

        if CHANNEL_EMAIL not in kept:
            kept.insert(0, CHANNEL_EMAIL)

        return tuple(kept)

    def channel_destination(self, channel: str) -> str | None:
        """Where a channel would actually deliver, or None if it cannot.

        Email deliberately returns None here: its address lives on the order or
        the organization, not on this row, and the dispatcher resolves it from
        there. Answering with a half-truth would make this look like the single
        source for every channel when it is not.
        """
        if channel == CHANNEL_TELEGRAM:
            return self.telegram_chat_id or None
        if channel == CHANNEL_WHATSAPP:
            return self.whatsapp_number or None
        return None

    @property
    def reachable_channels(self) -> tuple[str, ...]:
        """Chosen channels that have somewhere to send to.

        Choosing a channel and being able to use it are different facts. A
        customer can tick WhatsApp before supplying a number, and a dispatcher
        that trusted the tick alone would report a delivery that never happened.
        """
        return tuple(
            channel
            for channel in self.chosen_channels
            if channel == CHANNEL_EMAIL or self.channel_destination(channel)
        )

"""add follow-up channel preference and destinations

Follow-ups could only ever go to email, because email was the only thing the
project could send. With Telegram and WhatsApp arriving, a customer chooses where
their post-sale messages land — and may choose more than one.

Email is the default and is not removable. It is the address the purchase was
made with, so it is the one destination always on file; a customer who turned
every channel off would have silently opted out of their own onboarding.

The two destination columns are nullable on purpose. Choosing a channel and being
reachable on it are different facts: a customer can tick WhatsApp before
supplying a number, and WorkspaceProfile.reachable_channels is what decides
whether a listed channel can actually be used.

Backfilled to email, which is what every existing row already was.

Revision ID: f3b8d17c6a45
Revises: e7c1a94d5b32
Create Date: 2026-08-22 03:41:18.552104

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3b8d17c6a45'
down_revision: Union[str, Sequence[str], None] = 'e7c1a94d5b32'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default so existing rows satisfy NOT NULL without a separate
    # UPDATE, and so a row written by older application code still validates.
    op.add_column(
        "workspace_profiles",
        sa.Column(
            "follow_up_channels",
            sa.String(length=120),
            nullable=False,
            server_default="email",
        ),
    )
    op.add_column(
        "workspace_profiles",
        sa.Column("telegram_chat_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "workspace_profiles",
        sa.Column("whatsapp_number", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workspace_profiles", "whatsapp_number")
    op.drop_column("workspace_profiles", "telegram_chat_id")
    op.drop_column("workspace_profiles", "follow_up_channels")

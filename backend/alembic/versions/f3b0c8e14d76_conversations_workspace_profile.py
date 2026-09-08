"""Record which agent a conversation is talking to

Revision ID: f3b0c8e14d76
Revises: d1a7c93e5b40
Create Date: 2026-08-25

An organization used to own exactly one workspace profile, so "which config
governs this conversation" could be answered from the organization alone. That
stopped being true the moment a customer could buy both products: one workspace,
two agents, and ``resolve_config`` picking whichever profile was inserted first.

The visible symptom was a support widget answering under the sales agent's name.
The real one was permission — role is read from the profile column precisely so a
customer cannot promote their support agent, and resolving to the wrong profile
did it for them, handing a support widget the role that quotes prices and takes
money.

Nullable, no backfill. Null means "resolve by organization", which is the old
behaviour and is correct for the storefront (no profile at all) and harmless for
every thread written before two-agent workspaces existed.
"""

import sqlalchemy as sa
from alembic import op

revision = "f3b0c8e14d76"
down_revision = "d1a7c93e5b40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No FK constraint on SQLite: ALTER TABLE ADD COLUMN cannot carry one here,
    # and a batch rebuild of a live conversations table to gain a constraint the
    # application already enforces is the riskier trade. The ORM declares the
    # relationship; nothing writes this column but the widget route.
    op.add_column(
        "conversations",
        sa.Column("workspace_profile_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_conversations_workspace_profile_id",
        "conversations",
        ["workspace_profile_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_workspace_profile_id", table_name="conversations")
    op.drop_column("conversations", "workspace_profile_id")

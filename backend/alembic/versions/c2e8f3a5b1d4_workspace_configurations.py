"""Persist the buyer's agreed configuration per workspace profile

Revision ID: c2e8f3a5b1d4
Revises: e2f9a4c17b83
Create Date: 2026-09-10

The builder flow sends a configuration (channels, volume, integrations, languages,
workflow steps) that determines the price. That configuration was priced, written
to a quote, and then effectively lost: provisioning had to re-derive it from the
quote, and the agent's config and follow-ups had no place to read it.

This creates a `workspace_configurations` table with one row per workspace
profile, holding the buyer's agreed selection. Provisioning writes to it; the
agent config and follow-ups read from it. And adds `builder_config_hash` to
orders so the reusable-checkout lookup can match on the configuration shape.
"""

import sqlalchemy as sa
from alembic import op

revision = "c2e8f3a5b1d4"
down_revision = "e2f9a4c17b83"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_configurations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("channels", sa.String(length=120), nullable=False),
        sa.Column("monthly_conversations", sa.Integer(), nullable=True),
        sa.Column("integrations", sa.Integer(), nullable=False),
        sa.Column("languages", sa.String(length=200), nullable=False),
        sa.Column("workflow_steps", sa.Integer(), nullable=False),
        sa.Column("agreed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["workspace_profiles.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workspace_configurations_profile_id",
        "workspace_configurations",
        ["profile_id"],
    )
    op.add_column(
        "orders",
        sa.Column("builder_config_hash", sa.String(length=16), nullable=True),
    )
    op.create_index(
        "ix_orders_builder_config_hash",
        "orders",
        ["builder_config_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_orders_builder_config_hash", table_name="orders")
    op.drop_column("orders", "builder_config_hash")
    op.drop_index(
        "ix_workspace_configurations_profile_id",
        table_name="workspace_configurations",
    )
    op.drop_table("workspace_configurations")

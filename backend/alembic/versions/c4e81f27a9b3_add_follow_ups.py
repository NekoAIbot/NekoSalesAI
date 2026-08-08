"""add follow_ups

Revision ID: c4e81f27a9b3
Revises: b7c93d1e5a02
Create Date: 2026-08-08

The post-sale calendar. One row per scheduled message.

The unique constraint on (workspace_profile_id, rule_code) is doing real work:
scheduling runs on every payment-confirmation poll, and the browser polls the
status page roughly every 1.5 seconds. Without it a customer who left the
confirmation screen open would accumulate a duplicate calendar per poll.
"""

from alembic import op
import sqlalchemy as sa


revision = "c4e81f27a9b3"
down_revision = "b7c93d1e5a02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "follow_ups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("workspace_profile_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("rule_code", sa.String(length=60), nullable=False),
        sa.Column("day_offset", sa.Integer(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("reasoning_json", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_profile_id"],
            ["workspace_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_profile_id",
            "rule_code",
            name="uq_follow_ups_workspace_rule",
        ),
    )

    op.create_index(
        "ix_follow_ups_organization_id", "follow_ups", ["organization_id"]
    )
    op.create_index(
        "ix_follow_ups_workspace_profile_id",
        "follow_ups",
        ["workspace_profile_id"],
    )
    op.create_index("ix_follow_ups_order_id", "follow_ups", ["order_id"])
    op.create_index("ix_follow_ups_rule_code", "follow_ups", ["rule_code"])
    op.create_index("ix_follow_ups_status", "follow_ups", ["status"])

    # The due-queue query filters on status and orders by due_at. Indexed
    # because the desk hits it on every page load.
    op.create_index("ix_follow_ups_due_at", "follow_ups", ["due_at"])


def downgrade() -> None:
    op.drop_index("ix_follow_ups_due_at", table_name="follow_ups")
    op.drop_index("ix_follow_ups_status", table_name="follow_ups")
    op.drop_index("ix_follow_ups_rule_code", table_name="follow_ups")
    op.drop_index("ix_follow_ups_order_id", table_name="follow_ups")
    op.drop_index("ix_follow_ups_workspace_profile_id", table_name="follow_ups")
    op.drop_index("ix_follow_ups_organization_id", table_name="follow_ups")
    op.drop_table("follow_ups")

"""add orders and workspace profiles

Revision ID: b7c93d1e5a02
Revises: e2a5c31b7f48
Create Date: 2026-08-08

Two tables that together carry a customer from paying to running:

* orders freezes what was sold and at what price, keyed on the Paystack
  reference so repeated webhook deliveries land on the same row.
* workspace_profiles is the per-customer configuration of the one shared
  engine — the thing that replaces forking the codebase per customer.

Only the hash of an API key is stored, so this migration deliberately gives
api_key_hash no unique index it could be reversed through; the prefix column
exists so the UI can identify a key without holding one.
"""

import sqlalchemy as sa
from alembic import op

revision = "b7c93d1e5a02"
down_revision = "e2a5c31b7f48"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("paystack_reference", sa.String(length=100), nullable=False),
        sa.Column("checkout_url", sa.Text(), nullable=True),
        sa.Column("plan_code", sa.String(length=50), nullable=False),
        sa.Column("plan_name", sa.String(length=150), nullable=False),
        sa.Column("billing_period", sa.String(length=20), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("buyer_name", sa.String(length=150), nullable=True),
        sa.Column("buyer_email", sa.String(length=255), nullable=False),
        sa.Column("buyer_company", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_payload", sa.Text(), nullable=True),
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
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("paystack_reference", name="uq_orders_paystack_reference"),
    )
    op.create_index("ix_orders_id", "orders", ["id"])
    op.create_index("ix_orders_organization_id", "orders", ["organization_id"])
    op.create_index("ix_orders_conversation_id", "orders", ["conversation_id"])
    op.create_index(
        "ix_orders_paystack_reference", "orders", ["paystack_reference"], unique=True
    )
    op.create_index("ix_orders_buyer_email", "orders", ["buyer_email"])
    op.create_index("ix_orders_status", "orders", ["status"])

    op.create_table(
        "workspace_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("plan_code", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("agent_name", sa.String(length=100), nullable=False),
        sa.Column("company_name", sa.String(length=150), nullable=False),
        sa.Column("greeting", sa.Text(), nullable=False),
        sa.Column("tone", sa.String(length=40), nullable=False),
        sa.Column("accent_color", sa.String(length=20), nullable=False),
        sa.Column("api_key_hash", sa.String(length=128), nullable=True),
        sa.Column("api_key_prefix", sa.String(length=16), nullable=True),
        sa.Column("api_key_issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("widget_token", sa.String(length=64), nullable=True),
        sa.Column("steps_json", sa.Text(), nullable=True),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
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
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workspace_profiles_id", "workspace_profiles", ["id"])
    op.create_index(
        "ix_workspace_profiles_organization_id",
        "workspace_profiles",
        ["organization_id"],
        unique=True,
    )
    op.create_index("ix_workspace_profiles_order_id", "workspace_profiles", ["order_id"])
    op.create_index("ix_workspace_profiles_status", "workspace_profiles", ["status"])
    op.create_index(
        "ix_workspace_profiles_widget_token",
        "workspace_profiles",
        ["widget_token"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_workspace_profiles_widget_token", table_name="workspace_profiles")
    op.drop_index("ix_workspace_profiles_status", table_name="workspace_profiles")
    op.drop_index("ix_workspace_profiles_order_id", table_name="workspace_profiles")
    op.drop_index(
        "ix_workspace_profiles_organization_id", table_name="workspace_profiles"
    )
    op.drop_index("ix_workspace_profiles_id", table_name="workspace_profiles")
    op.drop_table("workspace_profiles")

    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_index("ix_orders_buyer_email", table_name="orders")
    op.drop_index("ix_orders_paystack_reference", table_name="orders")
    op.drop_index("ix_orders_conversation_id", table_name="orders")
    op.drop_index("ix_orders_organization_id", table_name="orders")
    op.drop_index("ix_orders_id", table_name="orders")
    op.drop_table("orders")

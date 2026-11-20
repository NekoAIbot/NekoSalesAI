"""Paystack financial integrity schema updates:
- Add last_reconciled_at and reconcile_attempts to orders
- Add credential_claims table for secure single-use claim tokens
- Add system_leases table for distributed reconciler lease coordination

Revision ID: a1c4e95d2f83
Revises: fbc42e917a61
"""
from alembic import op
import sqlalchemy as sa

revision = "a1c4e95d2f83"
down_revision = "fbc42e917a61"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Orders reconciliation tracking columns
    op.add_column("orders", sa.Column("last_reconciled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("reconcile_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.create_index("ix_orders_last_reconciled_at", "orders", ["last_reconciled_at"])

    # 2. Credential Claims table
    op.create_table(
        "credential_claims",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_credential_claims_id", "credential_claims", ["id"])
    op.create_index("ix_credential_claims_order_id", "credential_claims", ["order_id"])
    op.create_index("ix_credential_claims_user_id", "credential_claims", ["user_id"])
    op.create_index("ix_credential_claims_token_hash", "credential_claims", ["token_hash"], unique=True)

    # 3. System Leases table for distributed locking
    op.create_table(
        "system_leases",
        sa.Column("lease_name", sa.String(length=50), nullable=False),
        sa.Column("acquired_by", sa.String(length=100), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("lease_name"),
    )
    op.create_index("ix_system_leases_expires_at", "system_leases", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_system_leases_expires_at", table_name="system_leases")
    op.drop_table("system_leases")

    op.drop_index("ix_credential_claims_token_hash", table_name="credential_claims")
    op.drop_index("ix_credential_claims_user_id", table_name="credential_claims")
    op.drop_index("ix_credential_claims_order_id", table_name="credential_claims")
    op.drop_index("ix_credential_claims_id", table_name="credential_claims")
    op.drop_table("credential_claims")

    op.drop_index("ix_orders_last_reconciled_at", table_name="orders")
    op.drop_column("orders", "reconcile_attempts")
    op.drop_column("orders", "last_reconciled_at")

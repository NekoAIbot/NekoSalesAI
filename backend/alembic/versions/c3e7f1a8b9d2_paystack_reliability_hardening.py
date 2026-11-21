"""Paystack financial integrity reliability hardening:
- Add dispatch lease and attempt tracking columns to credential_claims
- Add unique constraint uq_credential_claims_order_id to credential_claims
- Add fencing_token to system_leases for distributed ownership fencing

Revision ID: c3e7f1a8b9d2
Revises: a1c4e95d2f83
"""
from alembic import op
import sqlalchemy as sa

revision = "c3e7f1a8b9d2"
down_revision = "a1c4e95d2f83"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Credential claims durable dispatch lease & retry tracking
    op.add_column(
        "credential_claims",
        sa.Column("dispatch_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "credential_claims",
        sa.Column("dispatch_last_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "credential_claims",
        sa.Column("dispatch_leased_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "credential_claims",
        sa.Column("dispatch_leased_by", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "credential_claims",
        sa.Column("dispatch_error", sa.String(length=500), nullable=True),
    )
    op.create_index(
        "ix_credential_claims_dispatch_leased_until",
        "credential_claims",
        ["dispatch_leased_until"],
    )
    op.create_unique_constraint(
        "uq_credential_claims_order_id",
        "credential_claims",
        ["order_id"],
    )

    # 2. System leases fencing token for distributed ownership fencing
    op.add_column(
        "system_leases",
        sa.Column("fencing_token", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("system_leases", "fencing_token")

    op.drop_constraint("uq_credential_claims_order_id", "credential_claims", type_="unique")
    op.drop_index("ix_credential_claims_dispatch_leased_until", table_name="credential_claims")
    op.drop_column("credential_claims", "dispatch_error")
    op.drop_column("credential_claims", "dispatch_leased_by")
    op.drop_column("credential_claims", "dispatch_leased_until")
    op.drop_column("credential_claims", "dispatch_last_attempt_at")
    op.drop_column("credential_claims", "dispatch_attempts")

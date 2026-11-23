"""Add encrypted_token to credential_claims for durable email retry.

Revision ID: d4f8e2a1b9c3
Revises: c3e7f1a8b9d2
"""
from alembic import op
import sqlalchemy as sa

revision = "d4f8e2a1b9c3"
down_revision = "c3e7f1a8b9d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "credential_claims",
        sa.Column("encrypted_token", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("credential_claims", "encrypted_token")

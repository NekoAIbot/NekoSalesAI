"""Add phone verification fields and hashed verification codes.

Revision ID: fbc42e917a61
Revises: a7f3c2e91d04
"""
from alembic import op
import sqlalchemy as sa

revision = "fbc42e917a61"
down_revision = "a7f3c2e91d04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone_number", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("phone_verified", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "phone_verification_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("code_hash", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_phone_verification_codes_code_hash", "phone_verification_codes", ["code_hash"])
    op.create_index("ix_phone_verification_codes_user_id", "phone_verification_codes", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_phone_verification_codes_user_id", table_name="phone_verification_codes")
    op.drop_index("ix_phone_verification_codes_code_hash", table_name="phone_verification_codes")
    op.drop_table("phone_verification_codes")
    op.drop_column("users", "phone_verified")
    op.drop_column("users", "phone_number")

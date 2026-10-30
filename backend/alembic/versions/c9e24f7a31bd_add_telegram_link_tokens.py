"""Single-use website to Telegram account link tokens.

Revision ID: c9e24f7a31bd
Revises: f3b0c8e14d76 + a1b2c3d4e5f6
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c9e24f7a31bd"
down_revision: Union[str, Sequence[str], None] = ("f3b0c8e14d76", "a1b2c3d4e5f6")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telegram_link_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_telegram_link_tokens_token_hash", "telegram_link_tokens", ["token_hash"], unique=True)
    op.create_index("ix_telegram_link_tokens_user_id", "telegram_link_tokens", ["user_id"])
    op.create_index("ix_telegram_link_tokens_organization_id", "telegram_link_tokens", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_telegram_link_tokens_organization_id", table_name="telegram_link_tokens")
    op.drop_index("ix_telegram_link_tokens_user_id", table_name="telegram_link_tokens")
    op.drop_index("ix_telegram_link_tokens_token_hash", table_name="telegram_link_tokens")
    op.drop_table("telegram_link_tokens")

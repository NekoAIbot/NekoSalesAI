"""Mira owner-memory and Telegram owner-link fields.

Revision ID: d2f4a8c1e907
Revises: c9e24f7a31bd
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d2f4a8c1e907"
down_revision: Union[str, Sequence[str], None] = "c9e24f7a31bd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("channel_identities") as batch_op:
        batch_op.add_column(sa.Column("owner_user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_channel_identities_owner_user_id_users", "users",
            ["owner_user_id"], ["id"], ondelete="SET NULL",
        )
    op.create_index("ix_channel_identities_owner_user_id", "channel_identities", ["owner_user_id"])
    op.create_table(
        "mira_memories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(length=160), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False, server_default="owner"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("organization_id", "key", name="uq_mira_memory_org_key"),
    )
    op.create_index("ix_mira_memories_organization_id", "mira_memories", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_mira_memories_organization_id", table_name="mira_memories")
    op.drop_table("mira_memories")
    op.drop_index("ix_channel_identities_owner_user_id", table_name="channel_identities")
    with op.batch_alter_table("channel_identities") as batch_op:
        batch_op.drop_constraint("fk_channel_identities_owner_user_id_users", type_="foreignkey")
        batch_op.drop_column("owner_user_id")

    op.drop_index("ix_channel_identities_owner_user_id", table_name="channel_identities")
    op.drop_column("channel_identities", "owner_user_id")

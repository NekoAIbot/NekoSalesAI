"""map messenger identities to conversations

A visitor in a browser carries their thread in the ``public_token`` the widget
was handed. Someone messaging on Telegram or WhatsApp carries nothing: every
delivery arrives with a chat id and no memory of the last one. Without this
table each message would open a fresh conversation, so the agent would greet the
same person forever and the stage machine would never advance past the first
turn.

The unique constraint is the point. Two rows for one chat id would mean two live
threads for one person and whichever the query found first would win.

``conversation_messages.external_id`` is a deduplication key, not a reference.
Both platforms deliver at least once and retry anything they do not see
acknowledged, so the same buyer question can arrive twice; the column is what
lets the second copy be dropped instead of answered. Nullable because the widget
has no such id — most rows in this table will never have one.

Revision ID: a4d2f8e91c67
Revises: f3b8d17c6a45
Create Date: 2026-08-22 08:12:44.310927

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4d2f8e91c67'
down_revision: Union[str, Sequence[str], None] = 'f3b8d17c6a45'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "channel_identities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=150), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "channel",
            "external_id",
            name="uq_channel_identity_per_org",
        ),
    )
    op.create_index(
        op.f("ix_channel_identities_id"), "channel_identities", ["id"]
    )
    op.create_index(
        op.f("ix_channel_identities_organization_id"),
        "channel_identities",
        ["organization_id"],
    )
    op.create_index(
        op.f("ix_channel_identities_conversation_id"),
        "channel_identities",
        ["conversation_id"],
    )

    op.add_column(
        "conversation_messages",
        sa.Column("external_id", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_conversation_messages_external_id",
        "conversation_messages",
        ["conversation_id", "external_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_conversation_messages_external_id", table_name="conversation_messages"
    )
    op.drop_column("conversation_messages", "external_id")

    op.drop_index(
        op.f("ix_channel_identities_conversation_id"),
        table_name="channel_identities",
    )
    op.drop_index(
        op.f("ix_channel_identities_organization_id"),
        table_name="channel_identities",
    )
    op.drop_index(op.f("ix_channel_identities_id"), table_name="channel_identities")
    op.drop_table("channel_identities")

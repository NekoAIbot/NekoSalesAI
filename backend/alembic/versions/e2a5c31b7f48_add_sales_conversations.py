"""add sales conversations and approval gate

Revision ID: e2a5c31b7f48
Revises: d1f4a7b92c30
Create Date: 2026-08-08

Adds the three tables behind the inbound sales loop: conversations (one
visitor thread), conversation_messages (turns, with the agent's reasoning
trail attached to each agent turn) and approval_requests (the human gate for
anything the published catalog does not cover).
"""

import sqlalchemy as sa
from alembic import op

revision = "e2a5c31b7f48"
down_revision = "d1f4a7b92c30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("public_token", sa.String(length=64), nullable=False),
        sa.Column("visitor_name", sa.String(length=150), nullable=True),
        sa.Column("visitor_email", sa.String(length=255), nullable=True),
        sa.Column("visitor_company", sa.String(length=255), nullable=True),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("lead_id", sa.Integer(), nullable=True),
        sa.Column("interested_plan_code", sa.String(length=50), nullable=True),
        sa.Column("handed_off_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("handoff_reason", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversations_id", "conversations", ["id"])
    op.create_index(
        "ix_conversations_organization_id", "conversations", ["organization_id"]
    )
    op.create_index(
        "ix_conversations_public_token",
        "conversations",
        ["public_token"],
        unique=True,
    )
    op.create_index("ix_conversations_stage", "conversations", ["stage"])
    op.create_index("ix_conversations_lead_id", "conversations", ["lead_id"])

    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("reasoning_json", sa.Text(), nullable=True),
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
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversation_messages_id", "conversation_messages", ["id"])
    op.create_index(
        "ix_conversation_messages_conversation_id",
        "conversation_messages",
        ["conversation_id"],
    )
    # Transcripts are always read as "this thread, in order", so the composite
    # index serves the only query shape that matters here.
    op.create_index(
        "ix_conversation_messages_conversation_id_id",
        "conversation_messages",
        ["conversation_id", "id"],
    )

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(length=150), nullable=False),
        sa.Column("requested", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("resolved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
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
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approval_requests_id", "approval_requests", ["id"])
    op.create_index(
        "ix_approval_requests_organization_id",
        "approval_requests",
        ["organization_id"],
    )
    op.create_index(
        "ix_approval_requests_conversation_id",
        "approval_requests",
        ["conversation_id"],
    )
    op.create_index("ix_approval_requests_status", "approval_requests", ["status"])


def downgrade() -> None:
    op.drop_table("approval_requests")
    op.drop_table("conversation_messages")
    op.drop_table("conversations")

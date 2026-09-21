"""Revision: add conversation context column

Conversation memory for the conversational-intelligence layer: business
facts, requirements, and conversation state extracted from the dialogue,
stored alongside the scope as the second structured half of the thread.
"""

revision: str = "b7c2d4e5f6a7"
down_revision: str = "8140458e7001"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("context_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversations", "context_json")

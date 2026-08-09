"""add quotes

Dynamic pricing needs somewhere to keep a priced requirement between "what
would this cost" and "I'll take it". The three fixed tiers did not: a plan code
named a catalog row the server could look the price up in. A computed price has
no catalog row.

What is stored is the requirement, not just the figure. The checkout re-prices
it server-side at order time, so ``total_minor`` here is evidence used to detect
a disagreement — never the source of a charge. Editing this column buys nothing.

Revision ID: a3f19c4d2b87
Revises: ceec502f790e
Create Date: 2026-08-09 09:41:02.118427

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f19c4d2b87'
down_revision: Union[str, Sequence[str], None] = 'ceec502f790e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quotes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reference", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("requirement_json", sa.Text(), nullable=False),
        sa.Column("product_type", sa.String(length=40), nullable=False),
        sa.Column("total_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
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
        sa.UniqueConstraint("reference", name="uq_quotes_reference"),
    )
    op.create_index("ix_quotes_id", "quotes", ["id"])
    op.create_index("ix_quotes_reference", "quotes", ["reference"], unique=True)
    op.create_index("ix_quotes_organization_id", "quotes", ["organization_id"])
    op.create_index("ix_quotes_conversation_id", "quotes", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_quotes_conversation_id", table_name="quotes")
    op.drop_index("ix_quotes_organization_id", table_name="quotes")
    op.drop_index("ix_quotes_reference", table_name="quotes")
    op.drop_index("ix_quotes_id", table_name="quotes")
    op.drop_table("quotes")

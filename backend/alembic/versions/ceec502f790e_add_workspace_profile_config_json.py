"""add workspace_profile.config_json

Gives each provisioned workspace its own product config — the plans, claims,
FAQs and identity its agent is permitted to say. Before this, the agent read
NekoSalesAI's own catalog no matter whose widget it was serving, so every
customer's buyers would have been quoted our price list.

Nullable, and no backfill. A profile with no config resolves to a minimal one
(see app.products.resolver): it can introduce itself and take a message, but
quotes nothing. That is the correct state for a workspace nobody has configured
yet — inventing plans for them here would be fabricating pricing.

Revision ID: ceec502f790e
Revises: d1f4a86b2c07
Create Date: 2026-08-09 07:22:13.661034

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ceec502f790e'
down_revision: Union[str, Sequence[str], None] = 'd1f4a86b2c07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workspace_profiles",
        sa.Column("config_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workspace_profiles", "config_json")

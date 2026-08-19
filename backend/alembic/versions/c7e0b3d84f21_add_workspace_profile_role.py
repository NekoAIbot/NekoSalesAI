"""add workspace_profiles.role

Which product a workspace is — the sales agent that can quote and take money,
or the support agent that must hand every commercial question over.

A column rather than a field inside config_json, and that placement is the
whole point. config_json is written by requirements intake, so anything stored
there is editable by the customer whose agent it governs. A role kept there
could be edited from "support_agent" to "sales_agent", which would promote a
support bot into one permitted to quote prices and raise payment links on its
owner's behalf. This column is written once at provisioning from the purchase
and intake cannot reach it.

Backfilled to sales_agent, which is what every existing row is: the support
agent did not exist before this release, so there is no row it could mislabel.

Revision ID: c7e0b3d84f21
Revises: a3f19c4d2b87
Create Date: 2026-08-19 12:58:41.203915

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7e0b3d84f21'
down_revision: Union[str, Sequence[str], None] = 'a3f19c4d2b87'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default so existing rows get a value without a separate UPDATE,
    # and so a row written by older application code still satisfies NOT NULL.
    op.add_column(
        "workspace_profiles",
        sa.Column(
            "role",
            sa.String(length=40),
            nullable=False,
            server_default="sales_agent",
        ),
    )


def downgrade() -> None:
    op.drop_column("workspace_profiles", "role")

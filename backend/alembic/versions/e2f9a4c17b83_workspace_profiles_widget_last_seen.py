"""Record when a customer's widget last actually ran

Revision ID: e2f9a4c17b83
Revises: a5271e0cb93d
Create Date: 2026-08-26

Everything the database knew about an install was what *we* did: a token minted,
a workspace marked ready, an email sent. Nothing recorded whether the snippet
ever executed on the customer's own site — which is the only fact that separates
"the code is not on your page yet" from "the code is running and we are looking
at the wrong thing".

Without it, every answer to "the chat isn't showing" is the same checklist, and a
customer who has already worked through the checklist gets nothing from being
handed it again. With it, the first line of the reply is something we can see.

Stamped by ``GET /api/v1/widget/{token}/config``, which can only be reached from a
page carrying the snippet, and throttled so a busy site does not pay per view for
a diagnostic that is read to the nearest few minutes.

Nullable with no backfill, and the null is meaningful rather than missing: it says
this workspace's snippet has not been seen running since this deployed. The
diagnosis treats a null as "not seen recently" rather than "definitely never
installed", so an existing customer is asked rather than accused.
"""

import sqlalchemy as sa
from alembic import op

revision = "e2f9a4c17b83"
down_revision = "a5271e0cb93d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspace_profiles",
        sa.Column("widget_last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workspace_profiles", "widget_last_seen_at")

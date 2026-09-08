"""Record when a buyer was actually told

Revision ID: d1a7c93e5b40
Revises: c4d81f6ba297
Create Date: 2026-08-24

An order carried three facts about how far a sale had got — paid, provisioned,
emailed — and none of them was "the person who paid knows". A real order was
verified, provisioned into a live workspace and sent a credentials email while
the buyer sat in the Telegram thread they had bought from, hearing nothing at
all. Every row in the database said the sale was complete.

``delivered_at`` is that missing fact, and it is stored rather than derived
because the reconciler has to be able to ask it before deciding to send. Nothing
else answers the question: provisioning being finished says the workspace exists,
a scheduled follow-up says an email was queued to an address, and neither means a
message reached the conversation the buyer is sitting in.

Nullable with no backfill on purpose. Existing paid orders read as undelivered,
which is true — they were — so the first reconcile after this deploys will tell
those buyers, once.
"""

import sqlalchemy as sa
from alembic import op

revision = "d1a7c93e5b40"
down_revision = "c4d81f6ba297"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("orders", "delivered_at")

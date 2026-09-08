"""Give follow_ups.created_at / updated_at the default the model promises.

Every other table has ``DEFAULT CURRENT_TIMESTAMP`` on these two columns.
``follow_ups`` was created without it while still being ``NOT NULL``, so any
insert that did not name a timestamp failed outright:

    sqlite3.IntegrityError: NOT NULL constraint failed: follow_ups.created_at

Nothing in the application names one. ``BaseModel`` declares both columns with
``server_default=func.now()`` and lets the database fill them, which is why no
code looked wrong and why the tests passed: they build the schema from the
models with ``create_all``, so the default was always there in tests and never
in the migrated database. The first real workspace to reach the follow-up step
took the failure — the insert poisoned the session, provisioning raised, the
checkout status endpoint returned 500, and the buyer's page sat on "setting up
your workspace now" with nothing behind it.

Zero rows exist to backfill: the table has never accepted a single insert.

SQLite cannot add a default to an existing column, so batch mode recreates the
table. ``c4e81f27a9b3`` is corrected in place as well, so a database built from
scratch is right the first time rather than being briefly wrong and repaired.

Revision ID: a5271e0cb93d
Revises: f3b0c8e14d76
"""

import sqlalchemy as sa
from alembic import op

revision = "a5271e0cb93d"
down_revision = "f3b0c8e14d76"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("follow_ups", recreate="always") as batch:
        batch.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            server_default=sa.func.now(),
        )
        batch.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            server_default=sa.func.now(),
        )


def downgrade() -> None:
    with op.batch_alter_table("follow_ups", recreate="always") as batch:
        batch.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            server_default=None,
        )
        batch.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            server_default=None,
        )

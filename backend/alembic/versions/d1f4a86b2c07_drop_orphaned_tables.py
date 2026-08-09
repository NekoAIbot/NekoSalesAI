"""drop tables orphaned by the removed AI stacks

Revision ID: d1f4a86b2c07
Revises: c4e81f27a9b3
Create Date: 2026-08-09

Thirteen tables whose models, services and routes were all deleted in
aa7037a, 4e33612 and the commit that carries this migration. Nothing reads or
writes them; app/models/__init__.py no longer registers them, so from here on
Base.metadata does not describe them either and a fresh database would never
create them. Dropping brings an existing database in line with that.

Data check before writing this: twelve of the thirteen were empty. The
thirteenth, ai_decision_logs, held one row — action NONE, reason "No action
required.", written by the DecisionEngine that no longer exists. An artifact of
the dead code, not a record anyone can use, and it goes with it.

The downgrade is deliberately not a reconstruction. Recreating thirteen tables
here would mean transcribing schemas whose models are gone from the tree, and
the result would be thirteen empty tables that no code addresses — the exact
state this migration exists to clean up. Downgrading past this point restores
the schema minus these tables, which is what every code path already expects.
"""

from alembic import op


revision = "d1f4a86b2c07"
down_revision = "c4e81f27a9b3"
branch_labels = None
depends_on = None


# Ordered so that anything holding a foreign key goes before the table it
# points at. SQLite tolerates any order here because it does not enforce the
# constraint on DROP by default; Postgres does not, and this needs to still be
# correct when DATABASE_URL is Postgres.
ORPHANED_TABLES = [
    "ai_execution_queue",
    "ai_thought_logs",
    "ai_decision_logs",
    "ai_memories",
    "ai_events",
    "ai_tasks",
    "worker_executions",
    "dead_letter_jobs",
    "mission_events",
    "priority_scores",
    "activity_events",
    "customer_timeline",
    "timeline_events",
]


def upgrade() -> None:
    for table in ORPHANED_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table}")


def downgrade() -> None:
    # Intentionally empty — see the module docstring.
    pass

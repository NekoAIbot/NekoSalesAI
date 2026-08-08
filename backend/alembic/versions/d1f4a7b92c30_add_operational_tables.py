"""add operational tables: activity_events, worker_executions, dead_letter_jobs

These three models existed but were never registered in app.models.__init__,
so Alembic never saw them and no migration was ever generated. Registering
them (this revision plus the __init__ import) makes the runtime tables that
BaseWorker, ExecutionLogger and DeadLetterQueue write to actually exist.

Revision ID: d1f4a7b92c30
Revises: 6c5aecc75706
Create Date: 2026-08-08 09:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1f4a7b92c30"
down_revision: Union[str, Sequence[str], None] = "6c5aecc75706"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "activity_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("source", sa.String(), server_default="AI"),
        sa.Column("priority", sa.String(), server_default="MEDIUM"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_activity_events_id", "activity_events", ["id"])
    op.create_index("ix_activity_events_customer_id", "activity_events", ["customer_id"])
    op.create_index("ix_activity_events_event_type", "activity_events", ["event_type"])

    op.create_table(
        "worker_executions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("worker_name", sa.String(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("success", sa.Boolean(), server_default=sa.false()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), server_default="0"),
        sa.Column("payload_json", sa.Text()),
        sa.Column("result_json", sa.Text()),
        sa.Column("error_message", sa.Text()),
        sa.Column("retry_count", sa.Integer(), server_default="0"),
        sa.Column("max_retries", sa.Integer(), server_default="3"),
        sa.Column("status", sa.String(), server_default="PENDING"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_worker_executions_id", "worker_executions", ["id"])
    op.create_index("ix_worker_executions_worker_name", "worker_executions", ["worker_name"])
    op.create_index("ix_worker_executions_customer_id", "worker_executions", ["customer_id"])

    op.create_table(
        "dead_letter_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("worker_name", sa.String(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("payload_json", sa.Text()),
        sa.Column("error_message", sa.Text()),
        sa.Column("status", sa.String(), server_default="FAILED"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_dead_letter_jobs_id", "dead_letter_jobs", ["id"])
    op.create_index("ix_dead_letter_jobs_worker_name", "dead_letter_jobs", ["worker_name"])
    op.create_index("ix_dead_letter_jobs_customer_id", "dead_letter_jobs", ["customer_id"])


def downgrade() -> None:
    op.drop_table("dead_letter_jobs")
    op.drop_table("worker_executions")
    op.drop_table("activity_events")

"""remember what a buyer said about the build being priced

Nera's own price is computed rather than looked up: a build costs what the work
in it costs, so the agent asks a handful of bounded questions and prices the
answers. Those answers have to survive between turns, and they cannot live in the
agent — ``compose_reply`` is pure by design, which is what makes its refusal to
invent a figure directly testable.

So the conversation carries them, the same way it already carries
``interested_plan_code``: the service reads the column, hands the value to the
pure engine, and writes back whatever the engine returns.

JSON in one nullable Text column rather than four typed ones. The scoping
questions are expected to change as the catalog grows, and a shape that changes
with the catalog should not need a migration each time. Nothing queries inside
it; it is read whole, by one module, which validates every field on the way in
(``Scope.from_json`` treats junk as "not answered yet" rather than raising, so a
bad row costs a buyer four questions instead of the conversation).

Null on every existing row, which is correct: they were all priced from a fixed
plan list.

Revision ID: b6e14c9d70a2
Revises: a4d2f8e91c67
Create Date: 2026-08-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6e14c9d70a2'
down_revision: Union[str, None] = 'a4d2f8e91c67'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("scope_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversations", "scope_json")

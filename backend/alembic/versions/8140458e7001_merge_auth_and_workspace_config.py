"""merge_auth_and_workspace_config

Revision ID: 8140458e7001
Revises: 7a1179b00001, c2e8f3a5b1d4
Create Date: 2026-09-12 15:00:53.776274

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8140458e7001'
down_revision: Union[str, Sequence[str], None] = ('7a1179b00001', 'c2e8f3a5b1d4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

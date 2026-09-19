"""add_auth_columns

Revision ID: 7a1179b00001
Revises: 3b486d4e5f76
Create Date: 2026-09-12 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7a1179b00001'
down_revision: Union[str, Sequence[str], None] = '3b486d4e5f76'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('email_verified', sa.Boolean(), server_default='0', nullable=False))
    op.add_column('users', sa.Column('totp_secret', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('totp_enabled', sa.Boolean(), server_default='0', nullable=False))
    op.add_column('users', sa.Column('recovery_codes', sa.String(length=2048), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'recovery_codes')
    op.drop_column('users', 'totp_enabled')
    op.drop_column('users', 'totp_secret')
    op.drop_column('users', 'email_verified')

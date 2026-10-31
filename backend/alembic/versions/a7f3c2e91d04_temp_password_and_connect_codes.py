"""temp password flag + telegram connect pending codes.

password_is_temp marks passwords issued out-of-band (telegram /connect): the
owner signs in once with it and is forced to replace it immediately.

telegram_connect_codes holds the pending email+code handshake for a chat that
wants to link before it has a web session to mint a link token from.

Revision ID: a7f3c2e91d04
Revises: ('b6e14c9d70a2', '6c5aecc75706', '8140458e7001')
Create Date: 2026-10-31 09:15:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7f3c2e91d04'
down_revision: Union[str, Sequence[str], None] = ('b6e14c9d70a2', '6c5aecc75706', '8140458e7001')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('password_is_temp', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )
    op.create_table(
        'telegram_connect_codes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('chat_id', sa.String(64), nullable=False, index=True),
        sa.Column('email_hash', sa.String(64), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('code_hash', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
    )
    op.create_index('ix_telegram_connect_codes_chat', 'telegram_connect_codes', ['chat_id'])


def downgrade() -> None:
    op.drop_index('ix_telegram_connect_codes_chat', table_name='telegram_connect_codes')
    op.drop_table('telegram_connect_codes')
    op.drop_column('users', 'password_is_temp')

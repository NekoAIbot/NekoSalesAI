"""index workspace_profiles.api_key_prefix

API keys are now verified on the server (app.auth.api_key), which happens on
every authenticated request a customer's integration makes. Verification narrows
by the stored prefix and then compares the full hash, so without this index the
narrowing step is a scan of every provisioned workspace on each call.

The prefix is not unique and must not be declared so: it is 12 characters of a
generated key, collisions are possible, and two workspaces sharing one is
harmless because the hash comparison still decides. A unique constraint here
would turn that harmless collision into a failed provisioning.

Revision ID: e7c1a94d5b32
Revises: c7e0b3d84f21
Create Date: 2026-08-21 09:14:02.118773

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e7c1a94d5b32'
down_revision: Union[str, Sequence[str], None] = 'c7e0b3d84f21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_workspace_profiles_api_key_prefix",
        "workspace_profiles",
        ["api_key_prefix"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workspace_profiles_api_key_prefix",
        table_name="workspace_profiles",
    )

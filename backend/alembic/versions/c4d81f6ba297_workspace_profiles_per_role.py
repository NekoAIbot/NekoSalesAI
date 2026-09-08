"""One organization can hold several agents

Revision ID: c4d81f6ba297
Revises: b6e14c9d70a2
Create Date: 2026-08-24

``workspace_profiles.organization_id`` was unique, from when a purchase meant
one agent and a customer meant one profile. Selling two products at once made
that constraint a delivery failure: provisioning creates one organization and
one profile per agent, so the second insert hit

    UNIQUE constraint failed: workspace_profiles.organization_id

and the whole transaction rolled back. A buyer who paid for a sales rep and a
support agent together received neither — and the confirmation page, which
re-attempts provisioning on every poll, kept saying "setting up your workspace
now" indefinitely while failing the same way each time. That happened to a real
₦148,000 order before this was found.

The replacement is a unique index on ``(organization_id, role)``. That keeps the
property the original was reaching for — no duplicate agent of the same kind in
one workspace, so a retried provision cannot double-deliver — while allowing the
one thing the product now sells: several different agents under one login.
"""

from alembic import op

revision = "c4d81f6ba297"
down_revision = "b6e14c9d70a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A plain index on organization_id stays, because every lookup of "this
    # customer's agents" narrows by it.
    op.drop_index("ix_workspace_profiles_organization_id", "workspace_profiles")
    op.create_index(
        "ix_workspace_profiles_organization_id",
        "workspace_profiles",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "uq_workspace_profiles_organization_role",
        "workspace_profiles",
        ["organization_id", "role"],
        unique=True,
    )


def downgrade() -> None:
    # Only reversible while no organization holds two agents. Going back with
    # two profiles in one workspace would fail on the unique index, which is the
    # correct outcome: the data no longer fits the old shape.
    op.drop_index(
        "uq_workspace_profiles_organization_role", "workspace_profiles"
    )
    op.drop_index("ix_workspace_profiles_organization_id", "workspace_profiles")
    op.create_index(
        "ix_workspace_profiles_organization_id",
        "workspace_profiles",
        ["organization_id"],
        unique=True,
    )

"""Saving a customer's requirements as their product config.

The write side of ``app.products.resolver``. An intake replaces the whole
config rather than patching fields, because a config is the complete set of
things the agent may say — a partial update would leave the old plans quotable
alongside the new ones, and the customer would have no way to remove a claim.

The storefront cannot be configured through this path. NekoSalesAI's own plans
and verified claims live in ``app.catalog.products`` as reviewable Python, and
a request that could rewrite them from a web form would be a way to change our
prices without a diff.

Neither can the product's *role*. An intake decides what the agent says; what
the agent is permitted to do was decided when the customer paid. A support
agent whose owner could set their own role could promote it into one that quotes
prices and takes money on their behalf, so ``save`` overwrites whatever role it
was handed with the one on the profile.
"""

from __future__ import annotations

from dataclasses import replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.logging import get_logger
from app.models.workspace_profile import WorkspaceProfile
from app.products.config import ProductConfig
from app.products.resolver import resolve_config
from app.products.serialization import config_to_json

logger = get_logger(__name__)


class IntakeError(ValueError):
    """The intake cannot be applied to this organization."""


class IntakeService:
    def __init__(self, db: Session):
        self.db = db

    def profile_for(
        self,
        organization_id: int,
        role: str | None = None,
    ) -> WorkspaceProfile | None:
        """The workspace profile an intake will write to.

        ``role`` is what makes this usable by a customer who bought both
        products. Without it this took ``.first()`` on the organization, which is
        the same defect ``resolve_config`` was fixed for: a workspace holding a
        sales agent and a support agent has two profiles, and whichever one the
        database returned first was the only one that could ever be configured.
        The other agent stayed on its empty starting config permanently, with no
        request the customer could make to reach it.

        Ordered by id when no role is named, so the no-role call is at least
        deterministic rather than depending on the query plan. A single-agent
        workspace — most of them — is unaffected either way.
        """
        query = select(WorkspaceProfile).where(
            WorkspaceProfile.organization_id == organization_id
        )

        if role is not None:
            query = query.where(WorkspaceProfile.role == role)

        return self.db.execute(
            query.order_by(WorkspaceProfile.id)
        ).scalars().first()

    def agents_for(self, organization_id: int) -> tuple[WorkspaceProfile, ...]:
        """Every agent this workspace holds, oldest first.

        A customer with two agents cannot configure either until they know which
        two they have, and nothing they were sent at purchase tells them. This is
        the list a settings page renders its selector from.
        """
        return tuple(
            self.db.execute(
                select(WorkspaceProfile)
                .where(WorkspaceProfile.organization_id == organization_id)
                .order_by(WorkspaceProfile.id)
            ).scalars()
        )

    def roles_for(self, organization_id: int) -> tuple[str, ...]:
        """Which agents this workspace holds, so a caller can name one."""
        return tuple(profile.role for profile in self.agents_for(organization_id))

    def current_config(
        self,
        organization_id: int,
        role: str | None = None,
    ) -> ProductConfig:
        """What this organization's agent is saying right now.

        ``role`` picks which agent, and matters for the same reason it does in
        ``profile_for``: resolving by organization alone in a two-agent workspace
        returns whichever profile is oldest, so a customer opening the support
        agent's settings would have been shown the sales agent's config — and
        saving that form would have copied one agent's answers onto the other.
        """
        profile = self.profile_for(organization_id, role) if role is not None else None

        return resolve_config(
            self.db,
            organization_id,
            profile.id if profile is not None else None,
        )

    def save(
        self,
        organization_id: int,
        config: ProductConfig,
        role: str | None = None,
    ) -> ProductConfig:
        """Replace this organization's config. Returns what was stored."""
        profile = self.profile_for(organization_id, role)

        if profile is None:
            raise IntakeError(
                "This organization has no provisioned workspace, so there is "
                "nothing to configure."
                if role is None
                else f"This workspace has no {role} to configure."
            )

        # The role is the profile's, not the payload's. An intake that could
        # set it would be a customer granting their own agent permission to
        # sell. Stored anyway so the row is self-describing, but stored as the
        # value the purchase decided.
        config = replace(config, role=profile.role)

        profile.config_json = config_to_json(config)
        # The profile's own identity columns feed the widget and the minimal
        # fallback, so they follow the config rather than drifting from it.
        profile.company_name = config.company_name
        profile.agent_name = config.agent_name

        self.db.commit()
        self.db.refresh(profile)

        logger.info(
            "Saved config for workspace %s: %s plan(s), %s claim(s)",
            profile.id,
            len(config.plans),
            len(config.capabilities),
        )

        # Read back through the resolver rather than returning the object we
        # were handed: what the customer sees must be what the engine will
        # read, including the provenance downgrade on stored claims.
        #
        # By profile id, not by organization. Reading back by organization was
        # the same guess ``profile_for`` was fixed for, one call deeper: a
        # two-agent workspace would have written the support agent's config and
        # then displayed the sales agent's, so a customer would have watched
        # their save appear to do nothing.
        return resolve_config(self.db, organization_id, profile.id)

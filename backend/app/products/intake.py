"""Saving a customer's requirements as their product config.

The write side of ``app.products.resolver``. An intake replaces the whole
config rather than patching fields, because a config is the complete set of
things the agent may say — a partial update would leave the old plans quotable
alongside the new ones, and the customer would have no way to remove a claim.

The storefront cannot be configured through this path. NekoSalesAI's own plans
and verified claims live in ``app.catalog.products`` as reviewable Python, and
a request that could rewrite them from a web form would be a way to change our
prices without a diff.
"""

from __future__ import annotations

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

    def profile_for(self, organization_id: int) -> WorkspaceProfile | None:
        return self.db.execute(
            select(WorkspaceProfile).where(
                WorkspaceProfile.organization_id == organization_id
            )
        ).scalars().first()

    def current_config(self, organization_id: int) -> ProductConfig:
        """What this organization's agent is saying right now."""
        return resolve_config(self.db, organization_id)

    def save(
        self,
        organization_id: int,
        config: ProductConfig,
    ) -> ProductConfig:
        """Replace this organization's config. Returns what was stored."""
        profile = self.profile_for(organization_id)

        if profile is None:
            raise IntakeError(
                "This organization has no provisioned workspace, so there is "
                "nothing to configure."
            )

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
        return resolve_config(self.db, organization_id)

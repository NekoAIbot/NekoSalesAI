"""Which config governs this conversation.

The engine is one piece of code serving many products, so every request has to
answer: whose rules apply here? Getting this wrong is not a cosmetic bug — it
means one customer's agent quoting another customer's prices to a buyer.

The rule is deliberately narrow. A conversation belongs to an organization. If
that organization has a provisioned workspace with a stored config, that config
governs. Otherwise it is the storefront's own organization, selling NekoSalesAI,
and ``STOREFRONT_CONFIG`` governs.

Note what is *not* here: a fallback from a customer's org to the storefront's
config. A provisioned workspace whose config row is missing or corrupt gets a
minimal config — its own name, no plans, no claims — which makes its agent
route everything to a human. An agent that says "let me get someone" is a bad
afternoon. An agent that quotes NekoSalesAI's ₦180,000 to a dental patient is a
refund and a lost customer.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import STOREFRONT_CONFIG
from app.config.logging import get_logger
from app.models.workspace_profile import WorkspaceProfile
from app.products.config import ProductConfig
from app.products.serialization import config_from_json

logger = get_logger(__name__)


def minimal_config(profile: WorkspaceProfile) -> ProductConfig:
    """The safest thing an agent can be: identity, and nothing to promise.

    Used when a workspace exists but its config does not parse. The agent can
    still say who it is and take a message; it cannot quote, claim or close.
    """
    return ProductConfig(
        company_name=profile.company_name,
        tagline="",
        description="",
        support_email="",
        agent_name=profile.agent_name or "the sales rep",
    )


def resolve_config(db: Session, organization_id: int) -> ProductConfig:
    """The config governing conversations owned by this organization."""
    profile = db.execute(
        select(WorkspaceProfile).where(
            WorkspaceProfile.organization_id == organization_id
        )
    ).scalars().first()

    # No workspace profile means this org is not a provisioned customer — it is
    # the storefront, selling NekoSalesAI itself.
    if profile is None:
        return STOREFRONT_CONFIG

    config = config_from_json(profile.config_json)

    if config is None:
        logger.warning(
            "Workspace %s has no usable config; falling back to a minimal one. "
            "Its agent will escalate every question.",
            profile.id,
        )
        return minimal_config(profile)

    return config

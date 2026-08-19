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

One field does not come from the stored config: ``role``. It is read from the
profile column, because ``config_json`` is written by requirements intake and a
customer who could edit their own role could promote a support agent into one
that quotes prices and takes money. What was bought decides what the agent may
do; what was typed into a form decides only what it says.
"""

from __future__ import annotations

from dataclasses import replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import STOREFRONT_CONFIG
from app.config.logging import get_logger
from app.models.workspace_profile import WorkspaceProfile
from app.products.config import PRODUCT_ROLES, ROLE_SUPPORT_AGENT, ProductConfig
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
        role=_role_of(profile),
    )


def _role_of(profile: WorkspaceProfile) -> str:
    """The role from the profile column, validated.

    A role outside the known set reads as a support agent rather than a sales
    agent. Everywhere else in this codebase an unrecognised value falls back to
    the sales agent for backwards compatibility, and that is right when the
    fallback only affects behaviour. Here it would affect *permission*: the
    sales agent is the role that can quote and take money, so guessing it from
    a corrupt column would be granting authority on the strength of junk.
    """
    if profile.role in PRODUCT_ROLES:
        return profile.role

    logger.error(
        "Workspace %s has an unrecognised role %r; treating it as a support "
        "agent so it cannot quote or sell.",
        profile.id,
        profile.role,
    )
    return ROLE_SUPPORT_AGENT


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

    # The role comes from the profile column, never from the stored JSON. That
    # JSON is written by requirements intake, so a role read out of it would be
    # a role the customer could edit — and editing it to "sales_agent" would
    # hand a support agent permission to quote prices and take money.
    role = _role_of(profile)

    if config.role != role:
        config = replace(config, role=role)

    return config

"""Which config governs this conversation.

The engine is one piece of code serving many products, so every request has to
answer: whose rules apply here? Getting this wrong is not a cosmetic bug — it
means one customer's agent quoting another customer's prices to a buyer.

The rule is deliberately narrow. A conversation belongs to an organization and,
once a workspace can hold more than one agent, to a profile within it. If the
caller names the profile — the widget route always can, since a widget token
belongs to exactly one agent — that profile's config governs. Otherwise the
organization's single profile governs. Otherwise it is the storefront's own
organization, selling NekoSalesAI, and ``STOREFRONT_CONFIG`` governs.

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
from app.products.config import BUILDABLE_ROLES, ROLE_SUPPORT_AGENT, ProductConfig
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

    Validated against ``BUILDABLE_ROLES`` rather than every role that exists.
    A workspace profile is a *customer's* product, and no customer's product is
    the builder — so a column reading "builder" is either corruption or an
    attempt at one, and either way it must not be honoured. Nera's own config is
    Python in ``app.catalog.products`` and never comes through here.
    """
    if profile.role in BUILDABLE_ROLES:
        return profile.role

    logger.error(
        "Workspace %s has an unrecognised role %r; treating it as a support "
        "agent so it cannot quote or sell.",
        profile.id,
        profile.role,
    )
    return ROLE_SUPPORT_AGENT


def resolve_config(
    db: Session,
    organization_id: int,
    profile_id: int | None = None,
) -> ProductConfig:
    """The config governing this conversation.

    ``profile_id`` says *which* of the organization's agents is being talked to,
    and is the accurate answer whenever the caller knows it — the widget route
    always does, because a widget token belongs to exactly one profile.

    Resolving by organization alone was correct while an organization owned one
    profile. A customer who buys both products owns two, in one workspace, and
    then "the org's config" is not a thing that exists. What it did instead was
    pick whichever profile was inserted first, which made a support widget answer
    under the sales agent's name — and under the sales agent's *role*, the one
    permitted to quote prices and take money. Guessing an identity is a cosmetic
    bug; guessing it from a set that includes a more privileged one is not.
    """
    profile = None

    if profile_id is not None:
        profile = _profile_by_id(db, profile_id, organization_id)

    if profile is None:
        profile = _only_profile(db, organization_id)

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


def _profile_by_id(
    db: Session,
    profile_id: int,
    organization_id: int,
) -> WorkspaceProfile | None:
    """The named profile, if it belongs to the organization that asked for it.

    The ownership check is the point. A profile id arriving with the wrong
    organization is either a bug in a caller or an attempt at one, and honouring
    it would be cross-tenant: one customer's agent answering with another
    customer's catalog, prices and claims. Refused, logged, and left to fall
    through to organization resolution — which is scoped to the right tenant even
    when it has to guess which of its agents.
    """
    profile = db.execute(
        select(WorkspaceProfile).where(WorkspaceProfile.id == profile_id)
    ).scalars().first()

    if profile is None:
        return None

    if profile.organization_id != organization_id:
        logger.error(
            "Workspace %s belongs to organization %s, not %s. Ignoring it: a "
            "config resolved across tenants would quote the wrong prices.",
            profile_id,
            profile.organization_id,
            organization_id,
        )
        return None

    return profile


def _only_profile(db: Session, organization_id: int) -> WorkspaceProfile | None:
    """This organization's profile, when there is no doubt which one it is.

    Ordered by id so the answer is at least deterministic, and logged when it is
    a guess. A workspace with two agents reaching here means some surface got to
    the engine without saying which agent it is — that is a bug at the caller,
    and the log line is how it gets found rather than lived with.
    """
    profiles = list(
        db.execute(
            select(WorkspaceProfile)
            .where(WorkspaceProfile.organization_id == organization_id)
            .order_by(WorkspaceProfile.id)
        ).scalars().all()
    )

    if not profiles:
        return None

    if len(profiles) > 1:
        logger.warning(
            "Organization %s has %s agents and nothing said which one this "
            "conversation is with; using %s (%s).",
            organization_id,
            len(profiles),
            profiles[0].agent_name,
            profiles[0].role,
        )

    return profiles[0]

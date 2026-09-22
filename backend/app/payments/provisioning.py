"""Provisioning: what happens the moment a payment lands."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import mail
from app.catalog import find_plan
from app.config.logging import get_logger
from app.core.security import hash_password
from app.models.configuration import WorkspaceConfiguration
from app.models.order import Order
from app.models.organization import Organization
from app.models.quote import Quote
from app.models.user import User
from app.pricing.complexity import (
    PRODUCT_NAMES,
    PRODUCT_SALES_AGENT,
    PRODUCT_SUPPORT_AGENT,
    PRODUCT_WORKFORCE_AGENT,
)
from app.pricing.quotes import QuoteService, reference_from_plan_code, requirement_from_json
from app.models.workspace_profile import (
    CHANNEL_EMAIL,
    CHANNEL_TELEGRAM,
    CHANNEL_WHATSAPP,
    FOLLOW_UP_CHANNELS,
    PROVISION_FAILED,
    PROVISION_READY,
    STEP_ADMIN,
    STEP_API_KEY,
    STEP_WIDGET,
    STEP_WORKSPACE,
    WorkspaceProfile,
)
from app.products.config import (
    ROLE_SALES_AGENT,
    ROLE_SUPPORT_AGENT,
    ProductConfig,
)
from app.products.serialization import config_to_json

logger = get_logger(__name__)

API_KEY_PREFIX = "nsk_live"
API_KEY_BYTES = 24
WIDGET_TOKEN_BYTES = 18

API_KEY_PREFIX_LENGTH = 12

TEMP_PASSWORD_BYTES = 12

_AGENT_FIRST_NAME = {
    ROLE_SALES_AGENT: "Ada",
    ROLE_SUPPORT_AGENT: "Remi",
}

CATALOG_ROLE = ROLE_SALES_AGENT


# Only the three purchasable products
PRODUCT_TYPE_TO_ROLE = {
    PRODUCT_SALES_AGENT: ROLE_SALES_AGENT,
    PRODUCT_SUPPORT_AGENT: ROLE_SUPPORT_AGENT,
    PRODUCT_WORKFORCE_AGENT: ROLE_SALES_AGENT,  # Workforce creates both roles
}

ROLE_TO_PRODUCT_TYPE = {
    role: product_type for product_type, role in PRODUCT_TYPE_TO_ROLE.items()
}


def hash_api_key(api_key: str) -> str:
    """SHA-256, not bcrypt.

    Deliberate, and the opposite of the right answer for passwords. An API key
    is 24 bytes of CSPRNG output with no dictionary to attack, so the slow
    hash buys nothing — and it has to be verified on every API request, where
    bcrypt's cost would become the endpoint's latency floor.
    """
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def _build_api_key() -> str:
    """A customer-facing API key."""
    return f"{API_KEY_PREFIX}_{secrets.token_hex(API_KEY_BYTES)}"


def _build_widget_token() -> str:
    """A token a customer embeds in their page source."""
    return secrets.token_urlsafe(WIDGET_TOKEN_BYTES)


def _build_temporary_password() -> str:
    """A one-time password for a customer who paid without choosing one."""
    return secrets.token_urlsafe(TEMP_PASSWORD_BYTES)


def _slugify(name: str) -> str:
    """Lowercase, keep letters and digits, collapse runs into single dashes."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:64]


def _role_for_order(order: Order, db: Session) -> str:
    """Which role to provision for a paid order."""
    if order.plan_code:
        reference = reference_from_plan_code(order.plan_code)
        if reference:
            try:
                quote = QuoteService(db).get(reference)
                if quote:
                    requirement = requirement_from_json(quote.requirement_json)
                    if requirement.products:
                        return PRODUCT_TYPE_TO_ROLE.get(
                            requirement.products[0], CATALOG_ROLE
                        )
            except Exception:
                pass
    return CATALOG_ROLE


def _starting_greeting(agent_name: str, company: str, role: str) -> str:
    """How the agent opens before the customer has configured anything.

    Role-specific because a greeting is a promise. A support agent that
    introduced itself as the sales rep would be inviting exactly the questions
    it is then going to refuse.
    """
    if role == ROLE_SUPPORT_AGENT:
        return (
            f"Hi \u2014 I'm {agent_name}, support for {company}. "
            "Tell me what you're stuck on and I'll help if I can."
        )

    return (
        f"Hi \u2014 I'm {agent_name}, the sales rep for {company}. "
        "Ask me anything about what we do."
    )


class ProvisioningError(RuntimeError):
    """We cannot tell what to build, so we will not build something."""


@dataclass(frozen=True)
class ProvisionedAgent:
    """One agent that was stood up, and the key that reaches it."""

    profile: WorkspaceProfile
    _api_key: str | None = None
    temporary_password: str | None = None

    @property
    def plan_code(self):
        return self.profile.plan_code

    @property
    def company_name(self):
        return self.profile.company_name

    @property
    def agent_name(self):
        return self.profile.agent_name

    @property
    def greeting(self):
        return self.profile.greeting

    @property
    def widget_token(self):
        return self.profile.widget_token

    @property
    def steps_json(self):
        return self.profile.steps_json

    @property
    def api_key(self):
        # Only reveal key on fresh provision, not idempotent lookups
        return self._api_key if self._api_key else None

    @property
    def api_key_prefix(self):
        return self.profile.api_key_prefix

    @property
    def organization_id(self):
        return self.profile.organization_id

    @property
    def organization(self):
        return self.profile.organization

    @property
    def role(self):
        return self.profile.role

    @property
    def id(self):
        return self.profile.id

    @property
    def status(self):
        return self.profile.status

    @property
    def api_key_hash(self):
        return self.profile.api_key_hash

    @property
    def temporary_password_hash(self):
        return self.profile.temporary_password_hash

    @property
    def is_ready(self) -> bool:
        """ProvisionedAgent delegates is_ready to its underlying profile."""
        return self.profile.is_ready

    @property
    def role(self) -> str:
        """ProvisionedAgent delegates role to its underlying profile."""
        return self.profile.role

    @property
    def status(self) -> str:
        """ProvisionedAgent delegates status to its underlying profile."""
        return self.profile.status


@dataclass(frozen=True)
class ProvisioningResult:
    """What one order's provisioning came to."""

    created: bool
    profiles: tuple = ()

    @property
    def api_key(self):
        """API key from the first freshly-provisioned profile.

        Returns None when this was an idempotent re-provision (no new keys).
        """
        if self.profiles and self.profiles[0].api_key:
            return self.profiles[0].api_key
        return None

    @property
    def temporary_password(self):
        if self.profiles:
            return self.profiles[0].temporary_password
        return None



class ProvisioningService:
    def __init__(self, db: Session):
        self.db = db

    def provision(self, order: Order) -> ProvisioningResult:
        """Stand up the workspace for a paid order. Idempotent.

        A renewal — the same buyer buying the same role again — reuses the
        existing profile (same widget token, same API key) and re-points it
        at the new order so delivery can find it by order_id.
        """
        if not order.is_paid:
            raise ValueError(
                f"Order {order.paystack_reference} has not been paid; "
                "refusing to provision an unpaid order."
            )

        # Check for exact order_id match first (idempotent re-provision)
        by_order = (
            self.db.execute(
                select(WorkspaceProfile).where(WorkspaceProfile.order_id == order.id)
            ).scalars().all()
        )
        if by_order:
            return ProvisioningResult(created=False, profiles=tuple(
                ProvisionedAgent(profile=p) for p in by_order
            ))

        # Check for renewal: same buyer, same role, different order. The
        # roles are read from the requirement — the full set, not the first
        # product's — because a repeat buyer ordering two products must not
        # have their old single profile re-pointed while the second agent
        # they paid for is never built.
        roles = self._roles_for_order(order)
        org = self._get_or_create_org(order)
        existing_by_role = {
            profile.role: profile
            for profile in (
                self.db.execute(
                    select(WorkspaceProfile).where(
                        WorkspaceProfile.organization_id == org.id,
                        WorkspaceProfile.role.in_(roles),
                    )
                ).scalars().all()
            )
        }
        missing = tuple(r for r in roles if r not in existing_by_role)

        if not missing:
            # A full renewal: every role this order paid for already exists.
            # Re-point each at the new order so delivery can find them by
            # order_id.
            renewed = []
            for role in roles:
                profile = existing_by_role[role]
                profile.order_id = order.id
                profile.plan_code = order.plan_code
                profile.status = PROVISION_READY
                renewed.append(ProvisionedAgent(profile=profile))
            self.db.commit()
            return ProvisioningResult(created=True, profiles=tuple(renewed))

        # A partial renewal — some roles exist, some are new. The existing
        # profiles are re-used (re-pointed, not duplicated: the org+role pair
        # is unique) and only the missing roles are built, so a buyer adding
        # a support agent to their sales workspace gets exactly one of each.
        agents = list(self._provision_for_role(order, missing))
        for role in roles:
            if role in existing_by_role:
                profile = existing_by_role[role]
                profile.order_id = order.id
                profile.plan_code = order.plan_code
                profile.status = PROVISION_READY
                agents.append(ProvisionedAgent(profile=profile))
        if agents:
            self.db.commit()

        if not agents:
            raise ProvisioningError(
                f"No agents provisioned for order {order.paystack_reference}."
            )

        return ProvisioningResult(created=True, profiles=tuple(agents))

    def _existing_profiles(self, order: Order) -> list[WorkspaceProfile]:
        """Find existing profiles for this order.

        Looks up by order_id first. If this is a renewal — the same buyer
        buying the same role again under a new order — also match on
        organization + role, so the existing profile is reused instead of
        violating the unique constraint and breaking the live agent.
        """
        by_order = (
            self.db.execute(
                select(WorkspaceProfile).where(WorkspaceProfile.order_id == order.id)
            )
            .scalars()
            .all()
        )
        if by_order:
            return list(by_order)

        # Renewal: find the buyer's organization and check for an existing
        # profile with the same role.
        role = _role_for_order(order, self.db)
        org = self._get_or_create_org(order)
        if org.id is None:
            return []
        return (
            self.db.execute(
                select(WorkspaceProfile).where(
                    WorkspaceProfile.organization_id == org.id,
                    WorkspaceProfile.role == role,
                )
            )
            .scalars()
            .all()
        )

    def _provision_for_role(
        self, order: Order, roles: tuple[str, ...]
    ) -> tuple[ProvisionedAgent, ...]:
        requirement = None
        if order.plan_code:
            reference = reference_from_plan_code(order.plan_code)
            if reference:
                try:
                    quote = QuoteService(self.db).get(reference)
                    if quote:
                        requirement = requirement_from_json(quote.requirement_json)
                except Exception as e:
                    logger.error(
                        "Order %s has an unreadable requirement: %s", order.paystack_reference, e
                    )

        if requirement is None:
            return ()

        agents: list[ProvisionedAgent] = []

        # The caller read the full role set from the requirement (Workforce
        # and multi-product orders expand to more than one role), so the
        # roles are built as given rather than re-derived here.
        roles_to_create = list(roles)

        for agent_role in roles_to_create:
            org = self._get_or_create_org(order)
            agent_name = self._agent_name(agent_role)

            profile = WorkspaceProfile(
                organization_id=org.id,
                order_id=order.id,
                plan_code=order.plan_code,
                role=agent_role,
                agent_name=agent_name,
                company_name=order.buyer_company or org.name,
                greeting=(
                    f"Hi, I'm {agent_name}. I'm the "
                    f"{'sales' if agent_role == ROLE_SALES_AGENT else 'support'} "
                    f"agent for {order.buyer_company or org.name}. How can I help?"
                ),
                widget_token=_build_widget_token(),
                status=PROVISION_READY,
            )

            # The moment the workspace went live. Every follow-up offset is
            # counted from this, and FollowUpService refuses to schedule
            # without it — a workspace that is ready but undated would never
            # hear from us again.
            profile.ready_at = datetime.now(timezone.utc)

            import json as _json
            from datetime import datetime as _dt, timezone as _tz
            from app.models.user import User as _User
            steps = {}
            steps[STEP_WORKSPACE] = _dt.now(_tz.utc).isoformat()

            self.db.add(profile)
            self.db.flush()
            steps[STEP_API_KEY] = _dt.now(_tz.utc).isoformat()

            api_key = _build_api_key()
            profile.api_key = api_key
            profile.api_key_prefix = api_key[:API_KEY_PREFIX_LENGTH]
            profile.api_key_hash = hash_api_key(api_key)
            profile.password_hash = hash_password(_build_temporary_password())
            steps[STEP_WIDGET] = _dt.now(_tz.utc).isoformat()

            # Create admin user for the workspace
            new_user_created = False
            if not self.db.execute(
                select(_User).where(_User.email == order.buyer_email)
            ).scalars().first():
                buyer_user = _User(
                    email=order.buyer_email,
                    full_name=order.buyer_name or order.buyer_email,
                    organization_id=org.id,
                    password_hash=hash_password(_build_temporary_password()),
                    is_admin=True,
                )
                self.db.add(buyer_user)
                new_user_created = True
            steps[STEP_ADMIN] = _dt.now(_tz.utc).isoformat()

            profile.steps_json = _json.dumps(steps)

            self.db.add(profile)
            self.db.flush()

            agents.append(
                ProvisionedAgent(
                    profile=profile,
                    _api_key=api_key,
                    temporary_password=_build_temporary_password() if new_user_created else None,
                )
            )

        if agents:
            self.db.commit()

        return tuple(agents)

    def rotate_api_key(self, agent: ProvisionedAgent) -> str:
        """Rotate the API key for an agent. Returns the new key."""
        api_key = _build_api_key()
        agent.profile.api_key = api_key
        agent.profile.api_key_prefix = api_key[:API_KEY_PREFIX_LENGTH]
        agent.profile.api_key_hash = hash_api_key(api_key)
        self.db.commit()
        return api_key

    def _get_or_create_org(self, order: Order) -> Organization:
        """Get the org for an order, or create one from buyer info.

        Matched on the buyer's *login* rather than on company name, because
        the login is what decides what they can see. Two real orders from one
        address once created two organizations (``nekosalesai`` and
        ``nekosalesai-2``) and the second purchase was invisible from the
        dashboard it was billed to. A second purchase on the same email is a
        returning customer adding to the workspace they already have, not a
        new tenant.

        Two *different* buyers who happen to name the same company must still
        get two workspaces — matching on company slug would silently merge
        strangers. So the only match is by login; everything else is a new
        org with a unique slug.
        """
        existing_user = (
            self.db.execute(
                select(User).where(User.email == order.buyer_email)
            ).scalars().first()
        )

        if existing_user is not None and existing_user.organization_id:
            existing_org = (
                self.db.execute(
                    select(Organization).where(
                        Organization.id == existing_user.organization_id
                    )
                ).scalars().first()
            )
            if existing_org is not None:
                return existing_org

        org_name = order.buyer_company or f"{order.buyer_email}'s Workspace"
        base_slug = _slugify(org_name)
        slug = base_slug
        suffix = 2
        while (
            self.db.execute(
                select(Organization.id).where(Organization.slug == slug)
            ).first()
            is not None
        ):
            slug = f"{base_slug}-{suffix}"
            suffix += 1

        org = Organization(name=org_name, slug=slug)
        self.db.add(org)
        self.db.flush()
        return org

    @staticmethod
    def _starting_config(company_name: str, role: str):
        """A new workspace's starting config — empty until a plan is chosen."""
        from app.products.config import ProductConfig
        return ProductConfig(
            company_name=company_name,
            tagline="",
            description="",
            support_email="",
            role=role,
            plans=(),
            capabilities=(),
        )

    def _agent_name(self, role: str) -> str:
        return _AGENT_FIRST_NAME.get(role, "Nera")

    def _roles_for_order(self, order: Order) -> tuple[str, ...]:
        """Which roles to provision for a paid order.

        Reads the stored requirement rather than the ``product_type`` column,
        because the column only holds the first product — reading it for a
        multi-product order would silently drop every product after the first.
        """
        if not order.plan_code:
            return (CATALOG_ROLE,)

        reference = reference_from_plan_code(order.plan_code)
        if not reference:
            return (CATALOG_ROLE,)

        try:
            quote = QuoteService(self.db).get(reference)
            if not quote:
                raise ProvisioningError(
                    f"Quote {reference} not found for order {order.paystack_reference}."
                )
            requirement = requirement_from_json(quote.requirement_json)
        except ProvisioningError:
            raise
        except Exception as exc:
            raise ProvisioningError(
                f"Could not read requirement for order {order.paystack_reference}: {exc}"
            ) from exc

        if requirement.products:
            # Workforce is one product that builds two agents — the sales and
            # the support role — so it expands here, at the single place that
            # translates products into roles. Everything downstream (renewal
            # matching, profile creation) then sees the true role set.
            roles = []
            for product in requirement.products:
                if product == PRODUCT_WORKFORCE_AGENT:
                    roles.extend((ROLE_SALES_AGENT, ROLE_SUPPORT_AGENT))
                else:
                    roles.append(PRODUCT_TYPE_TO_ROLE.get(product, CATALOG_ROLE))
            roles = tuple(dict.fromkeys(roles))
        else:
            product = requirement.product_type
            if product == PRODUCT_WORKFORCE_AGENT:
                roles = (ROLE_SALES_AGENT, ROLE_SUPPORT_AGENT)
            else:
                roles = (PRODUCT_TYPE_TO_ROLE.get(product, CATALOG_ROLE),)

        for role in roles:
            if role not in PRODUCT_TYPE_TO_ROLE.values():
                raise ProvisioningError(
                    f"Role {role!r} has no buildable product mapping."
                )

        return roles

    def get_for_order(self, order: Order) -> WorkspaceProfile | None:
        """Get the primary workspace profile for an order."""
        profiles = self._existing_profiles(order)
        if not profiles:
            return None
        return profiles[0]


def provision_order(db: Session, order: Order) -> ProvisioningResult:
    """Convenience function for provisioning an order."""
    return ProvisioningService(db).provision(order)

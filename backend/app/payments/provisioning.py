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
    """Hash an API key for storage."""
    return hash_password(api_key)


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


@dataclass(frozen=True)
class ProvisioningResult:
    """What one order's provisioning came to."""

    created: bool
    profiles: tuple = ()

    @property
    def temporary_password(self):
        if self.profiles:
            return self.profiles[0].temporary_password
        return None



class ProvisioningService:
    def __init__(self, db: Session):
        self.db = db

    def provision(self, order: Order) -> ProvisioningResult:
        """Stand up the workspace for a paid order. Idempotent."""
        if not order.is_paid:
            raise ValueError(
                f"Order {order.paystack_reference} has not been paid; "
                "refusing to provision an unpaid order."
            )

        existing = self._existing_profiles(order)
        if existing:
            return ProvisioningResult(created=False, profiles=tuple(
                ProvisionedAgent(profile=p) for p in existing
            ))

        role = _role_for_order(order, self.db)
        agents = self._provision_for_role(order, role)

        if not agents:
            raise ProvisioningError(
                f"No agents provisioned for order {order.paystack_reference}."
            )

        return ProvisioningResult(created=True, profiles=agents)

    def _existing_profiles(self, order: Order) -> list[WorkspaceProfile]:
        """Find existing profiles for this order by order_id."""
        return (
            self.db.execute(
                select(WorkspaceProfile).where(WorkspaceProfile.order_id == order.id)
            )
            .scalars()
            .all()
        )

    def _provision_for_role(
        self, order: Order, role: str
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

        # For Workforce, create both sales and support agents
        roles_to_create = [role]
        if requirement.product_type == PRODUCT_WORKFORCE_AGENT:
            roles_to_create = [ROLE_SALES_AGENT, ROLE_SUPPORT_AGENT]
        elif requirement.products and len(requirement.products) > 1:
            roles_to_create = [
                PRODUCT_TYPE_TO_ROLE.get(p, CATALOG_ROLE) for p in requirement.products
            ]

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
        """Get the org for an order, or create one from buyer info."""
        org_name = order.buyer_company or f"{order.buyer_email}'s Workspace"
        slug = _slugify(org_name)

        org = (
            self.db.execute(
                select(Organization).where(Organization.slug == slug)
            )
            .scalars()
            .first()
        )

        if org is None:
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

    def get_for_order(self, order: Order) -> WorkspaceProfile | None:
        """Get the primary workspace profile for an order."""
        profiles = self._existing_profiles(order)
        if not profiles:
            return None
        return profiles[0]


def provision_order(db: Session, order: Order) -> ProvisioningResult:
    """Convenience function for provisioning an order."""
    return ProvisioningService(db).provision(order)

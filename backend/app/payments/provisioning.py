"""Provisioning: what happens the moment a payment lands.

The promise on the landing page is that a customer is live within seconds of
paying, so this runs inline on the confirming request rather than on a queue.
That is a deliberate trade at this size — a background worker would add a
moving part between the money and the thing the money bought, and the four
steps here are all local database writes.

Idempotent throughout. The webhook and the browser return page both call it,
often within the same second, and provisioning twice would hand a customer two
workspaces and two API keys.

The API key is generated once and shown once. Only its hash is stored, so a
customer who loses it gets a new one rather than a copy — there is no copy.
"""

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
from app.models.order import Order
from app.models.organization import Organization
from app.models.quote import Quote
from app.models.user import User
from app.pricing.complexity import (
    PRODUCT_NAMES,
    PRODUCT_SALES_AGENT,
    PRODUCT_SUPPORT_AGENT,
)
from app.pricing.quotes import reference_from_plan_code, requirement_from_json
from app.models.workspace_profile import (
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

# How much of a key is stored in the clear. Two jobs: the dashboard shows it so a
# customer can tell which key is which, and app.auth.api_key narrows its lookup
# by it so verifying a key is an indexed read rather than a scan of every
# workspace. Both sides must agree, so the length is named here rather than
# spelled 12 in each place.
API_KEY_PREFIX_LENGTH = 12

# Length of the one-time password generated for a customer who paid without
# choosing one. Long enough not to be guessed, and it is emailed rather than
# shown, so its readability does not matter.
TEMP_PASSWORD_BYTES = 12

# The name each product introduces itself with. Only a default — the customer
# renames it during intake — but it should not be a sales rep's name on a
# support agent.
_AGENT_FIRST_NAME = {
    ROLE_SALES_AGENT: "Ada",
    ROLE_SUPPORT_AGENT: "Remi",
}

# A plan code that is not a quote reference belongs to a fixed tier, and every
# fixed tier that has ever existed on this storefront sold the sales agent. The
# storefront publishes none now — everything it sells is quoted — so this is the
# fallback for orders placed before that change, not the common path. A
# quote-backed order names its product explicitly, and ``_role_for_order`` reads
# it from the quote rather than guessing from text.
CATALOG_ROLE = ROLE_SALES_AGENT


# Pricing's product types and the engine's roles are separate vocabularies
# that happen to share spellings today. Mapping them explicitly keeps the
# layers independent, and means a product the factory learns to *price*
# before it can *build* fails loudly here instead of resolving to a role by
# coincidence.
PRODUCT_TYPE_TO_ROLE = {
    PRODUCT_SALES_AGENT: ROLE_SALES_AGENT,
    PRODUCT_SUPPORT_AGENT: ROLE_SUPPORT_AGENT,
}

# The way back, for naming an agent in an email. Derived rather than written out
# so it cannot fall out of step with the map above.
ROLE_TO_PRODUCT_TYPE = {
    role: product_type for product_type, role in PRODUCT_TYPE_TO_ROLE.items()
}


class ProvisioningError(RuntimeError):
    """We cannot tell what to build, so we will not build something."""


@dataclass(frozen=True)
class ProvisionedAgent:
    """One agent that was stood up, and the key that reaches it.

    ``api_key`` is the only place that plaintext key ever exists. It is
    returned to the caller for immediate display and then it is gone.
    """

    profile: WorkspaceProfile
    api_key: str | None


@dataclass(frozen=True)
class ProvisionResult:
    """What provisioning produced.

    An order may have bought more than one agent, so ``agents`` is the whole
    truth and ``profile``/``api_key`` are the first of them. Both spellings
    exist because most callers — the follow-up scheduler, the receipt — act
    once per purchase rather than once per agent, and reading ``.profile`` is
    what they mean. Anything that must touch every agent reads ``agents``.
    """

    agents: tuple[ProvisionedAgent, ...]
    temporary_password: str | None
    created: bool

    @property
    def profile(self) -> WorkspaceProfile:
        return self.agents[0].profile

    @property
    def api_key(self) -> str | None:
        return self.agents[0].api_key

    @property
    def profiles(self) -> tuple[WorkspaceProfile, ...]:
        return tuple(agent.profile for agent in self.agents)


def hash_api_key(key: str) -> str:
    """SHA-256, not bcrypt.

    Deliberate, and the opposite of the right answer for passwords. An API key
    is 24 bytes of CSPRNG output with no dictionary to attack, so the slow
    hash buys nothing — and it has to be verified on every API request, where
    bcrypt's cost would become the endpoint's latency floor.
    """
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "workspace"


def _starting_greeting(agent_name: str, company: str, role: str) -> str:
    """How the agent opens before the customer has configured anything.

    Role-specific because a greeting is a promise. A support agent that
    introduced itself as the sales rep would be inviting exactly the questions
    it is then going to refuse.
    """
    if role == ROLE_SUPPORT_AGENT:
        return (
            f"Hi — I'm {agent_name}, support for {company}. "
            "Tell me what you're stuck on and I'll help if I can."
        )

    return (
        f"Hi — I'm {agent_name}, the sales rep for {company}. "
        "Ask me anything about what we do."
    )


class ProvisioningService:
    def __init__(self, db: Session):
        self.db = db

    def provision(self, order: Order) -> ProvisionResult:
        """Stand up everything the paid order entitles the buyer to."""
        if not order.is_paid:
            raise ValueError(
                "Refusing to provision an order that has not been paid."
            )

        existing = self.db.execute(
            select(WorkspaceProfile)
            .where(WorkspaceProfile.order_id == order.id)
            .order_by(WorkspaceProfile.id)
        ).scalars().all()

        if existing:
            # Already done. The keys are not returned because they only ever
            # existed in the first call's memory — a second call cannot produce
            # them, and returning None says so rather than implying a lost key
            # can be recovered.
            return ProvisionResult(
                agents=tuple(
                    ProvisionedAgent(profile=profile, api_key=None)
                    for profile in existing
                ),
                temporary_password=None,
                created=False,
            )

        plan = find_plan(order.plan_code)
        company = (order.buyer_company or order.plan_name or "").strip()
        if not company:
            company = order.buyer_email.split("@", 1)[0]

        steps: dict[str, str] = {}

        try:
            # Before anything is created: if we cannot tell which products were
            # bought, there is nothing correct to build.
            roles = self._roles_for_order(order)

            organization = self._organization_for(company, order)
            self._stamp(steps, STEP_WORKSPACE)

            # One organization and one login however many agents were bought —
            # the customer bought several agents, not several companies. Each
            # agent gets its own profile, role, greeting and API key, because
            # those are the things that differ between a sales rep and a support
            # desk and sharing them would make one of the two wrong.
            temporary_password = self._create_admin(order, organization)
            self._stamp(steps, STEP_ADMIN)

            agents: list[ProvisionedAgent] = []

            for role in roles:
                agent_name = _AGENT_FIRST_NAME[role]

                # A returning customer buying an agent they already have.
                #
                # Reused rather than duplicated, and its credentials left alone.
                # The customer's site is serving the widget token they already
                # pasted into it, so minting a replacement would take their live
                # agent off their page as the reward for buying again. The key is
                # theirs until they rotate it.
                existing_profile = self._profile_for_role(organization.id, role)

                if existing_profile is not None:
                    existing_profile.order_id = order.id
                    existing_profile.plan_code = order.plan_code
                    existing_profile.status = PROVISION_READY

                    logger.info(
                        "Order %s renews the %s this workspace already has; "
                        "keeping its key and widget token.",
                        order.paystack_reference,
                        role,
                    )

                    agents.append(
                        ProvisionedAgent(profile=existing_profile, api_key=None)
                    )
                    continue

                profile = WorkspaceProfile(
                    organization_id=organization.id,
                    order_id=order.id,
                    plan_code=order.plan_code,
                    role=role,
                    agent_name=agent_name,
                    company_name=organization.name,
                    greeting=_starting_greeting(
                        agent_name, organization.name, role
                    ),
                    config_json=config_to_json(
                        self._starting_config(organization.name, role)
                    ),
                )
                self.db.add(profile)
                self.db.flush()

                api_key = self._issue_api_key(profile)
                self._stamp(steps, STEP_API_KEY)

                profile.widget_token = secrets.token_urlsafe(WIDGET_TOKEN_BYTES)
                self._stamp(steps, STEP_WIDGET)

                profile.steps_json = json.dumps(steps)
                profile.status = PROVISION_READY
                profile.ready_at = datetime.now(timezone.utc)

                agents.append(
                    ProvisionedAgent(profile=profile, api_key=api_key)
                )

            if plan is not None:
                organization.subscription_plan = plan.code
                organization.currency = plan.currency

            self.db.commit()

            for agent in agents:
                self.db.refresh(agent.profile)

            logger.info(
                "Provisioned workspace %s with %d agent(s) for order %s (%s)",
                organization.slug,
                len(agents),
                order.paystack_reference,
                order.buyer_email,
            )

            result = ProvisionResult(
                agents=tuple(agents),
                temporary_password=temporary_password,
                created=True,
            )

            # After the commit, and deliberately so. The secrets in this email
            # exist nowhere else — only their hashes are stored — so the send has
            # to happen while they are still in memory. Doing it before the
            # commit would risk mailing credentials for a workspace that then
            # failed to save.
            self._send_credentials(order, result)

            return result

        except Exception as exc:
            # A half-built workspace is worse than none: the customer would
            # get a login to something that does not work. Roll back, then
            # record the failure on its own so the desk can see it.
            self.db.rollback()

            logger.exception(
                "Provisioning failed for order %s", order.paystack_reference
            )

            self._record_failure(order, str(exc))
            raise

    # ---------- steps ----------

    def _send_credentials(self, order: Order, result: ProvisionResult) -> None:
        """Mail the customer their login, key and embed snippet.

        Never raises. The money has already moved and the workspace already
        exists by the time this runs, so a mail server having a bad minute must
        not turn a successful purchase into an exception — the customer would see
        a failure for something that actually worked. A failed send is logged
        with the profile id so the desk can resend.

        This is also the only moment the plaintext API key and temporary password
        exist. Both are stored as hashes, so there is nothing to look up later:
        if this email does not arrive, the answer is a reset, not a copy.
        """
        if not order.buyer_email:
            logger.warning(
                "No buyer email on order %s; credentials not sent.",
                order.paystack_reference,
            )
            return

        message = mail.credentials(
            to=order.buyer_email,
            company_name=result.profile.company_name,
            temporary_password=result.temporary_password,
            agents=tuple(
                mail.AgentCredentials(
                    label=PRODUCT_NAMES.get(
                        ROLE_TO_PRODUCT_TYPE.get(agent.profile.role, ""),
                        agent.profile.role,
                    ),
                    api_key=agent.api_key,
                    widget_token=agent.profile.widget_token,
                )
                for agent in result.agents
            ),
            workspace_profile_id=result.profile.id,
        )

        outcome = mail.send(message)

        if not outcome.sent:
            logger.error(
                "Credentials email failed for workspace %s (order %s): %s",
                result.profile.id,
                order.paystack_reference,
                outcome.error,
            )

    def _roles_for_order(self, order: Order) -> tuple[str, ...]:
        """Which products this order bought, in the order they were quoted.

        A catalog plan is always the sales agent. A quote-backed order carries
        ``quote_<reference>`` as its plan code, and the products are read from
        that stored quote's requirement — the JSON we wrote when we priced it,
        which is also what the checkout re-priced to decide the amount. Not the
        quote's ``product_type`` column, which holds only the first of them: a
        buyer who paid for two agents and was handed one would be short-changed
        by exactly the amount that column cannot represent.

        Raises when the quote is missing, unreadable, or names a product we have
        no role for. Guessing here would mean guessing what the customer paid
        for, and both guesses are wrong in a way that matters: defaulting to the
        sales agent hands a support buyer something that can take money on their
        behalf, and defaulting to support silently under-delivers. The caller
        turns this into a recorded provisioning failure the desk can see.
        """
        reference = reference_from_plan_code(order.plan_code)

        if reference is None:
            return (CATALOG_ROLE,)

        quote = self.db.execute(
            select(Quote).where(Quote.reference == reference)
        ).scalars().first()

        if quote is None:
            raise ProvisioningError(
                f"Order {order.paystack_reference} was bought against quote "
                f"{reference!r}, which no longer exists. We cannot tell which "
                "product to build."
            )

        try:
            requirement = requirement_from_json(quote.requirement_json)
        except (ValueError, KeyError, TypeError) as exc:
            raise ProvisioningError(
                f"Quote {reference} has a requirement we cannot read, so we "
                "cannot tell what to build."
            ) from exc

        roles: list[str] = []
        for product_type in requirement.products:
            role = PRODUCT_TYPE_TO_ROLE.get(product_type)

            if role is None:
                raise ProvisioningError(
                    f"Quote {reference} is for {product_type!r}, which the "
                    "factory can price but cannot yet provision."
                )

            roles.append(role)

        return tuple(roles)

    def _starting_config(self, company: str, role: str) -> ProductConfig:
        """The config a brand-new workspace begins with.

        Empty of plans, claims and facts on purpose. We know the customer's
        name because they paid us; we know nothing about what they sell. Their
        agent introduces itself and routes every substantive question to them
        until they fill this in — which is Stage B's job.

        The alternative, seeding it with plausible-looking plans, would mean
        their agent quoting prices no human ever set. Better an agent that
        says "let me get someone" than one that invents a number.

        ``role`` is what makes this the factory rather than one product with a
        variable name on it: a support agent gets a config that will refuse
        commercial questions no matter what is later added to its price list.
        """
        return ProductConfig(
            company_name=company,
            tagline=f"Ask me anything about {company}.",
            description="",
            support_email="",
            agent_name=f"{_AGENT_FIRST_NAME[role]} from {company}",
            role=role,
        )

    def _organization_for(self, company: str, order: Order) -> Organization:
        """The buyer's workspace: the one they already have, or a new one.

        A second purchase on the same email used to create a second
        organization. That is not what buying again means, and the consequence
        was not cosmetic: the buyer's login points at their *first* organization,
        so the agents they had just paid for were provisioned somewhere their
        account could not see. Two real orders from one address did exactly this
        — ``nekosalesai`` and ``nekosalesai-2`` — and the second purchase was
        invisible from the dashboard it was billed to.

        Matched on the buyer's login rather than on the organization's email
        column, because the login is what decides what they can see, and that is
        the thing that was wrong. An address with no account is a new customer,
        whatever any organization row happens to say.
        """
        existing = self.db.execute(
            select(User).where(User.email == order.buyer_email)
        ).scalars().first()

        if existing is not None and existing.organization_id:
            organization = self.db.execute(
                select(Organization).where(
                    Organization.id == existing.organization_id
                )
            ).scalars().first()

            if organization is not None:
                logger.info(
                    "Order %s is a returning buyer; adding to workspace %s "
                    "rather than creating a second one.",
                    order.paystack_reference,
                    organization.slug,
                )
                return organization

        return self._create_organization(company, order)

    def _profile_for_role(self, organization_id: int, role: str) -> WorkspaceProfile | None:
        return self.db.execute(
            select(WorkspaceProfile).where(
                WorkspaceProfile.organization_id == organization_id,
                WorkspaceProfile.role == role,
            )
        ).scalars().first()

    def _create_organization(self, company: str, order: Order) -> Organization:
        organization = Organization(
            name=company,
            slug=self._unique_slug(company),
            email=order.buyer_email,
            subscription_plan=order.plan_code,
            currency=order.currency,
        )

        self.db.add(organization)
        self.db.flush()
        return organization

    def _create_admin(self, order: Order, organization: Organization) -> str | None:
        """Give the buyer a login, unless that email already has one.

        An existing account means a returning customer buying a second
        workspace. Creating a duplicate user would break the unique email
        constraint and, worse, would reset the password on an account they
        are already using.
        """
        existing = self.db.execute(
            select(User).where(User.email == order.buyer_email)
        ).scalars().first()

        if existing is not None:
            return None

        password = secrets.token_urlsafe(TEMP_PASSWORD_BYTES)

        user = User(
            email=order.buyer_email,
            full_name=order.buyer_name or order.buyer_email.split("@", 1)[0],
            password_hash=hash_password(password),
            organization_id=organization.id,
            is_admin=True,
            is_active=True,
        )

        self.db.add(user)
        self.db.flush()

        return password

    def _issue_api_key(self, profile: WorkspaceProfile) -> str:
        raw = secrets.token_urlsafe(API_KEY_BYTES)
        key = f"{API_KEY_PREFIX}_{raw}"

        profile.api_key_hash = hash_api_key(key)
        profile.api_key_prefix = key[:API_KEY_PREFIX_LENGTH]
        profile.api_key_issued_at = datetime.now(timezone.utc)

        return key

    def rotate_api_key(self, profile: WorkspaceProfile) -> str:
        """Issue a new key, invalidating the old one immediately."""
        key = self._issue_api_key(profile)
        self.db.commit()
        self.db.refresh(profile)
        return key

    # ---------- helpers ----------

    @staticmethod
    def _stamp(steps: dict[str, str], step: str) -> None:
        steps[step] = datetime.now(timezone.utc).isoformat()

    def _unique_slug(self, name: str) -> str:
        base = _slugify(name)
        slug = base
        suffix = 2

        while self._slug_exists(slug):
            slug = f"{base}-{suffix}"
            suffix += 1

        return slug

    def _slug_exists(self, slug: str) -> bool:
        return (
            self.db.execute(
                select(Organization.id).where(Organization.slug == slug)
            ).first()
            is not None
        )

    def _record_failure(self, order: Order, reason: str) -> None:
        """Leave a trace of the failure without a workspace attached.

        Recorded against a placeholder organization would be misleading, so
        this only writes if a profile row already exists for the order.
        """
        profile = self.db.execute(
            select(WorkspaceProfile).where(WorkspaceProfile.order_id == order.id)
        ).scalars().first()

        if profile is None:
            return

        profile.status = PROVISION_FAILED
        profile.failure_reason = reason[:2_000]
        self.db.commit()

    def get_for_order(self, order: Order) -> WorkspaceProfile | None:
        return self.db.execute(
            select(WorkspaceProfile).where(WorkspaceProfile.order_id == order.id)
        ).scalars().first()

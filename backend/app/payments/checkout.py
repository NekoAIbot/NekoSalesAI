"""Checkout: turning an agreed plan into a paid order.

The rules this service exists to enforce:

* The amount comes from the pricing engine, never from the request.
* Confirmation is idempotent and keyed on the Paystack reference.
* A charge is only accepted if the amount and currency Paystack reports match what the order says.
* When a buyer arrives through the builder with a full configuration, that configuration is persisted and priced server-side.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import mail
from app.config.logging import get_logger
from app.config.settings import settings
from app.models.conversation import STAGE_CLOSED_WON, Conversation
from app.models.configuration import WorkspaceConfiguration
from app.models.order import ORDER_PAID, ORDER_PENDING, Order
from app.models.quote import Quote
from app.models.workspace_profile import WorkspaceProfile
from app.payments import Charge, PaystackClient, PaystackError, PaymentsNotConfigured, dump_payload
from app.pricing.complexity import Plan, PricingError, Requirement, price
from app.pricing.quotes import QuoteError, QuoteService, build_reference as build_quote_reference, _requirement_to_dict
from app.products.config import ROLE_SALES_AGENT, ROLE_SUPPORT_AGENT
from app.products.resolver import resolve_config

logger = get_logger(__name__)

# Prefix makes an order recognisable at a glance in the Paystack dashboard.
REFERENCE_PREFIX = "neko"
REFERENCE_BYTES = 12

# How much of the configuration hash to store.
CONFIG_HASH_BYTES = 16


class CheckoutError(ValueError):
    """The checkout cannot be created as asked."""


def build_reference() -> str:
    return f"{REFERENCE_PREFIX}_{secrets.token_hex(REFERENCE_BYTES)}"


def _config_hash(builder_requirement: dict) -> str:
    """A stable hash of the builder configuration for reusable-checkout lookup."""
    normalised = {
        "product_type": builder_requirement.get("product_type", "").strip().lower(),
        "products": sorted(c.strip().lower() for c in builder_requirement.get("products", []) if c.strip()),
        "channels": sorted(c.strip().lower() for c in builder_requirement.get("channels", []) if c.strip()),
        "integrations": sorted(c.strip().lower() for c in builder_requirement.get("integrations", []) if c.strip()),
        "languages": sorted(c.strip().lower() for c in builder_requirement.get("languages", []) if c.strip()),
        "monthly_conversations": int(builder_requirement.get("monthly_conversations", 500)),
    }
    return hashlib.sha256(
        json.dumps(normalised, sort_keys=True).encode("utf-8")
    ).hexdigest()[:CONFIG_HASH_BYTES * 2]


def _builder_to_requirement(builder_requirement: dict) -> Requirement:
    """Convert a builder configuration dict into a priceable Requirement.

    The builder sends a dict. The pricing engine needs a Requirement. This is
    the translation layer.
    """
    products = tuple(
        c.strip()
        for c in builder_requirement.get("products", [])
        if c.strip()
    ) or (builder_requirement.get("product_type", "sales_agent"),)

    channels = tuple(
        c.strip().lower()
        for c in builder_requirement.get("channels", [])
        if c.strip()
    ) or ("web",)

    integrations = tuple(
        c.strip().lower()
        for c in builder_requirement.get("integrations", [])
        if c.strip()
    )

    languages = tuple(
        c.strip().lower()
        for c in builder_requirement.get("languages", [])
        if c.strip()
    )

    return Requirement(
        product_type=products[0] if products else "sales_agent",
        products=products,
        channels=channels,
        integrations=integrations,
        languages=languages,
        monthly_conversations=int(builder_requirement.get("monthly_conversations", 500)),
    )


class CheckoutService:
    def __init__(self, db: Session, client: PaystackClient | None = None):
        self.db = db
        self.client = client or PaystackClient()

    # ---------- creating ----------

    def create_order(
        self,
        *,
        organization_id: int,
        plan_code: str | None = None,
        quote_reference: str | None = None,
        buyer_email: str,
        buyer_name: str | None = None,
        buyer_company: str | None = None,
        conversation: Conversation | None = None,
        product_type: str | None = None,
        products: tuple[str, ...] = (),
        channels: tuple[str, ...] = (),
        integrations: tuple[str, ...] = (),
        languages: tuple[str, ...] = (),
        monthly_conversations: int = 500,
    ) -> Order:
        """Create a pending order and its payment link."""
        # Build the builder_requirement dict if the buyer sent configuration.
        builder_requirement = None
        if any([product_type, products, channels, integrations, languages]):
            builder_requirement = {
                "product_type": product_type or "sales_agent",
                "products": list(products),
                "channels": list(channels),
                "integrations": list(integrations),
                "languages": list(languages),
                "monthly_conversations": monthly_conversations,
            }

        plan = self._resolve_plan(
            plan_code, quote_reference, builder_requirement
        )

        email = (buyer_email or "").strip()
        if not email:
            raise CheckoutError(
                "An email address is required to raise a payment."
            )

        existing = self._reusable_order(
            organization_id, plan, email, conversation,
            builder_requirement,
        )
        if existing is not None:
            return existing

        reference = build_reference()

        order = Order(
            organization_id=organization_id,
            conversation_id=conversation.id if conversation else None,
            paystack_reference=reference,
            plan_code=plan.code,
            plan_name=plan.name,
            billing_period=plan.billing_period,
            amount_minor=plan.amount_minor,
            currency=plan.currency,
            buyer_name=(buyer_name or "").strip() or None,
            buyer_email=email,
            buyer_company=(buyer_company or "").strip() or None,
            status=ORDER_PENDING,
        )

        # Persist the builder configuration hash for reusable-checkout lookup.
        if builder_requirement is not None:
            order.builder_config_hash = _config_hash(builder_requirement)
            self._store_builder_configuration(builder_requirement, order)
            # Also create a Quote row so provisioning can look up the requirement.
            try:
                requirement = _builder_to_requirement(builder_requirement)
                computed = price(requirement)
                quote = Quote(
                    reference=build_quote_reference(),
                    organization_id=organization_id,
                    conversation_id=conversation.id if conversation else None,
                    requirement_json=json.dumps(_requirement_to_dict(requirement)),
                    product_type=requirement.product_type,
                    total_minor=computed.total_minor,
                    currency=computed.currency,
                )
                self.db.add(quote)
            except Exception:
                logger.warning(
                    "Order %s: could not persist quote for builder configuration",
                    reference,
                )

        checkout = self.client.initialize(
            email=email,
            amount_minor=plan.amount_minor,
            currency=plan.currency,
            reference=reference,
            callback_url=(
                f"{settings.PUBLIC_BASE_URL.rstrip('/')}"
                f"/checkout/return?reference={reference}"
            ),
            metadata={
                "plan_code": plan.code,
                "organization_id": organization_id,
                "conversation_id": conversation.id if conversation else None,
            },
        )

        order.checkout_url = checkout.authorization_url

        if checkout.reference and checkout.reference != reference:
            order.paystack_reference = checkout.reference

        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)

        logger.info(
            "Order %s created: %s %s for %s",
            order.paystack_reference,
            plan.code,
            plan.display_price,
            email,
        )

        return order

    def _resolve_plan(
        self,
        plan_code: str | None,
        quote_reference: str | None,
        builder_requirement: dict | None = None,
    ) -> Plan:
        """Turn whichever identifier the caller sent into a priced plan."""
        code = (plan_code or "").strip() or None
        reference = (quote_reference or "").strip() or None

        if code and reference:
            raise CheckoutError(
                "Send either a plan code or a quote reference, not both."
            )

        if reference:
            try:
                _, plan = QuoteService(self.db).redeem(reference)
            except QuoteError as exc:
                raise CheckoutError(str(exc)) from exc
            return plan

        if builder_requirement is not None:
            try:
                requirement = _builder_to_requirement(builder_requirement)
                computed = price(requirement)
            except PricingError as exc:
                raise CheckoutError(str(exc)) from exc

            return Plan(
                code="quote_" + build_quote_reference(),
                name=computed.product_name,
                audience="",
                currency=computed.currency,
                amount_minor=computed.total_minor,
                billing_period=computed.billing_period,
                seats=1,
                monthly_conversation_limit=computed.monthly_conversation_limit,
                features=tuple(
                    item.label for item in computed.line_items
                    if item.dimension not in ("base", "discount")
                ),
            )

        if not code:
            raise CheckoutError(
                "A plan code, a quote reference, or a builder configuration is required."
            )

        from app.catalog import find_plan
        plan = find_plan(code)
        if plan is None:
            raise CheckoutError(f"There is no plan with the code {code!r}.")

        return plan

    def _reusable_order(
        self,
        organization_id: int,
        plan: Plan,
        email: str,
        conversation: Conversation | None,
        builder_requirement: dict | None = None,
    ) -> Order | None:
        """An existing pending order for the same buyer and the same plan."""
        stmt = (
            select(Order)
            .where(
                Order.organization_id == organization_id,
                Order.buyer_email == email,
                Order.plan_code == plan.code,
                Order.status == ORDER_PENDING,
                Order.amount_minor == plan.amount_minor,
            )
            .order_by(Order.id.desc())
        )

        if builder_requirement is not None:
            stmt = stmt.where(
                Order.builder_config_hash == _config_hash(builder_requirement)
            )

        if conversation is not None:
            stmt = stmt.where(Order.conversation_id == conversation.id)

        order = self.db.execute(stmt).scalars().first()

        if order is not None and not order.checkout_url:
            return None

        return order

    def _store_builder_configuration(
        self, builder_requirement: dict, order: Order
    ) -> None:
        """Persist the buyer's agreed configuration on the workspace."""
        try:
            requirement = _builder_to_requirement(builder_requirement)
        except (ValueError, TypeError):
            logger.warning(
                "Order %s: builder configuration is unreadable.",
                order.paystack_reference,
            )
            return

        profiles = self.db.execute(
            select(WorkspaceProfile).where(
                WorkspaceProfile.order_id == order.id
            )
        ).scalars().all()

        for profile in profiles:
            existing = self.db.execute(
                select(WorkspaceConfiguration).where(
                    WorkspaceConfiguration.profile_id == profile.id
                )
            ).scalars().first()

            if existing is not None:
                existing.channels = ",".join(requirement.channels)
                existing.monthly_conversations = requirement.monthly_conversations
                existing.integrations = ",".join(requirement.integrations)
                existing.languages = ",".join(requirement.languages)
                existing.agreed_at = datetime.now(timezone.utc)
            else:
                config = WorkspaceConfiguration(
                    profile_id=profile.id,
                    channels=",".join(requirement.channels),
                    monthly_conversations=requirement.monthly_conversations,
                    integrations=",".join(requirement.integrations),
                    languages=",".join(requirement.languages),
                    agreed_at=datetime.now(timezone.utc),
                )
                self.db.add(config)

        self.db.commit()

    # ---------- confirming ----------

    def get_by_reference(
        self,
        reference: str,
        organization_id: int | None = None,
    ) -> Order | None:
        stmt = select(Order).where(Order.paystack_reference == reference)

        if organization_id is not None:
            stmt = stmt.where(Order.organization_id == organization_id)

        return self.db.execute(stmt).scalars().first()

    def confirm(self, charge: Charge) -> Order | None:
        """Record a successful charge against its order."""
        order = self.get_by_reference(charge.reference)

        if order is None:
            logger.warning(
                "Charge %s does not match any order; ignoring.",
                charge.reference,
            )
            return None

        if order.is_paid:
            return order

        if not charge.paid:
            logger.info(
                "Charge %s reported status %r; leaving order pending.",
                charge.reference,
                charge.status,
            )
            return order

        if not self._amount_matches(order, charge):
            logger.error(
                "Charge %s claims %s %s but order %s is %s %s.",
                charge.reference,
                charge.amount_minor,
                charge.currency,
                order.id,
                order.amount_minor,
                order.currency,
            )
            return order

        order.status = ORDER_PAID
        order.paid_at = datetime.now(timezone.utc)
        order.provider_payload = dump_payload(charge.raw)

        if order.conversation is not None:
            order.conversation.stage = STAGE_CLOSED_WON

        self.db.commit()
        self.db.refresh(order)

        logger.info(
            "Order %s paid: %s for %s",
            order.paystack_reference,
            order.plan_code,
            order.buyer_email,
        )

        self._send_receipt(order)

        return order

    def confirm_by_reference(self, reference: str) -> Order | None:
        """Verify a payment with Paystack by reference and confirm the order."""
        client = self.client if self.client else PaystackClient()
        order = self.get_by_reference(reference)
        if order is None:
            return None
        if order.is_paid:
            return order
        if not settings.payments_enabled:
            raise PaymentsNotConfigured("Payments are not configured")
        try:
            charge = client.verify(reference)
        except Exception as e:
            logger.warning("Could not verify %s: %s", reference, e)
            return order
        return self.confirm(charge)

    def _amount_matches(self, order: Order, charge: Charge) -> bool:
        """Check that what Paystack reports matches what we charged."""
        return (
            charge.currency == order.currency
            and charge.amount_minor == order.amount_minor
        )

    def _send_receipt(self, order: Order) -> None:
        """Email the buyer their receipt. Never fails the request."""
        try:
            from app.mail.messages import receipt as build_receipt
            from app.mail.transport import send

            send(build_receipt(
                to=order.buyer_email,
                company_name=order.buyer_company or order.buyer_email,
                plan_name=order.plan_name,
                amount_minor=order.amount_minor,
                currency=order.currency,
                reference=order.paystack_reference,
            ))
        except Exception:
            logger.exception(
                "Could not send receipt for order %s", order.paystack_reference
            )

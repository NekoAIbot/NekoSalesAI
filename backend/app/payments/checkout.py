"""Checkout: turning an agreed plan into a paid order.

The rules this service exists to enforce:

* The amount comes from the catalog, never from the request. A checkout
  endpoint that accepts an amount is a checkout endpoint that can be asked to
  charge ₦1 for the annual plan.
* Confirmation is idempotent and keyed on the Paystack reference. The webhook
  will arrive more than once — Paystack retries, and the browser callback can
  race it — so "already paid" is a normal outcome, not an error.
* A charge is only accepted if the amount and currency Paystack reports match
  what the order says. A confirmation that disagrees about money is not a
  confirmation; it is logged and refused.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import mail
from app.catalog import Plan, find_plan
from app.config.logging import get_logger
from app.config.settings import settings
from app.models.conversation import STAGE_CLOSED_WON, Conversation
from app.models.order import ORDER_PAID, ORDER_PENDING, Order
from app.payments import Charge, PaystackClient, PaystackError, dump_payload
from app.pricing.quotes import QuoteError, QuoteService

logger = get_logger(__name__)

# Prefix makes an order recognisable at a glance in the Paystack dashboard.
REFERENCE_PREFIX = "neko"
REFERENCE_BYTES = 12


class CheckoutError(ValueError):
    """The checkout cannot be created as asked."""


def build_reference() -> str:
    return f"{REFERENCE_PREFIX}_{secrets.token_hex(REFERENCE_BYTES)}"


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
    ) -> Order:
        """Create a pending order and its payment link.

        The plan is resolved server-side and its price copied onto the order.
        Nothing about the amount is taken from the caller: a catalog plan code
        is looked up, and a quote reference is re-priced from the requirement
        we stored (see ``app.pricing.quotes``). Both hand back a ``Plan``, so
        everything downstream of this line is identical either way.
        """
        plan = self._resolve_plan(plan_code, quote_reference)

        email = (buyer_email or "").strip()
        if not email:
            raise CheckoutError("An email address is required to raise a payment.")

        existing = self._reusable_order(organization_id, plan, email, conversation)
        if existing is not None:
            # The buyer asked twice, or refreshed. Re-showing the same link is
            # both cheaper and less confusing than stacking pending orders.
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

        # Paystack echoes the reference back; if it ever differs, theirs is
        # the one the webhook will carry, so theirs is the one we store.
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
        self, plan_code: str | None, quote_reference: str | None
    ) -> Plan:
        """Turn whichever identifier the caller sent into a priced plan.

        Exactly one identifier, because two would mean choosing between them,
        and the cheaper-wins or first-wins rule that implies is a discount the
        buyer set. A quote reference is re-priced here rather than read: see
        ``QuoteService.redeem``.
        """
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

        if not code:
            raise CheckoutError("A plan code or a quote reference is required.")

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

        if conversation is not None:
            stmt = stmt.where(Order.conversation_id == conversation.id)

        order = self.db.execute(stmt).scalars().first()

        # A pending order with no link is unusable — it means initialize()
        # failed after the row was written. Let a fresh one be created.
        if order is not None and not order.checkout_url:
            return None

        return order

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
        """Record a successful charge against its order.

        Idempotent: a second delivery of the same charge returns the order
        unchanged rather than double-provisioning. Returns None when the
        reference is unknown, which is what a webhook aimed at the wrong
        deployment looks like.
        """
        order = self.get_by_reference(charge.reference)

        if order is None:
            logger.warning(
                "Charge %s does not match any order; ignoring.", charge.reference
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
                "Charge %s claims %s %s but order %s is %s %s; refusing to "
                "mark it paid.",
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

        # Inside the `if order.is_paid: return` guard above, so a webhook and a
        # browser return arriving together cannot send two receipts. Non-fatal:
        # the payment is recorded either way, and a receipt that failed to send
        # is a message to resend, not a charge to reverse.
        self._send_receipt(order)

        return order

    def _send_receipt(self, order: Order) -> None:
        """Confirm to the buyer that money moved and what it bought.

        Every value is read off the order, including the plan name. The order
        recorded what it was sold as at the time of sale, so a receipt built from
        it cannot drift if the catalog is edited later — and a quote-backed order
        with no catalog plan needs no special case.
        """
        if not order.buyer_email:
            return

        outcome = mail.send(
            mail.receipt(
                to=order.buyer_email,
                company_name=order.buyer_company or order.buyer_name or "your team",
                plan_name=order.plan_name,
                amount_minor=order.amount_minor,
                currency=order.currency,
                reference=order.paystack_reference,
            )
        )

        if not outcome.sent:
            logger.error(
                "Receipt failed for order %s: %s",
                order.paystack_reference,
                outcome.error,
            )

    @staticmethod
    def _amount_matches(order: Order, charge: Charge) -> bool:
        if charge.amount_minor != order.amount_minor:
            return False

        # Paystack echoes the currency it charged in. An empty string means
        # an older payload shape rather than a mismatch, so it is not treated
        # as a disagreement.
        if charge.currency and charge.currency.upper() != order.currency.upper():
            return False

        return True

    def confirm_by_reference(self, reference: str) -> Order | None:
        """Verify a reference with Paystack, then confirm it.

        Used by the browser return page. The redirect proves nothing on its
        own, so the provider is asked directly before anything is marked paid.
        """
        order = self.get_by_reference(reference)
        if order is None:
            return None

        if order.is_paid:
            return order

        try:
            charge = self.client.verify(reference)
        except PaystackError as exc:
            logger.warning("Could not verify %s: %s", reference, exc)
            return order

        return self.confirm(charge)

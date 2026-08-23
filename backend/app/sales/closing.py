"""Turning a conversation that reached a price into a link that can be paid.

The gap this closes was a false promise. Nera ends a successful conversation
with "the next thing you'll see is their secure page" — true in the browser,
where the widget sees ``ready_to_buy``, posts to
``/conversations/{token}/checkout`` and redirects, and false everywhere else. A
buyer who did the whole intake on Telegram was told payment was coming and then
heard nothing, because no code path existed to raise one. That is the worst kind
of bug in a sales agent: it looks like a closed deal from the inside and reads as
being ignored from the outside.

So the close lives here, once, and every channel calls it. Not in
``app.messaging.service`` — that file composes no product sentences on purpose,
and a link with a price beside it is a product sentence. Not in the web route
either, which is where it used to be trapped.

Four rules this module exists to keep:

*The price is never taken from the caller.* It is re-derived from the stored
requirement by ``CheckoutService``, the same path the widget uses. A channel
cannot ask for a cheaper link than the one it was quoted.

*A link is offered once.* An order carries its own checkout url, so a thread that
already has one is not re-sent it on every subsequent turn. Asking again is a
separate, explicit act — see ``resend``.

*What the buyer received is in the transcript.* A link sent on a channel but
missing from the thread would leave a human reviewing the conversation unable to
see the most consequential message in it.

*A failure is said out loud.* Every way this can fail — payments switched off, a
quote that no longer prices, the provider being down — returns text a buyer can
act on rather than silence. Silence is what made the original bug so expensive:
nothing in the transcript showed anything had gone wrong.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.logging import get_logger
from app.models.conversation import (
    ROLE_AGENT,
    STAGE_READY_TO_BUY,
    Conversation,
    Message,
)
from app.models.order import ORDER_PENDING, Order
from app.payments import PaymentsNotConfigured, PaystackError
from app.payments.checkout import CheckoutError, CheckoutService
from app.pricing.quotes import reference_from_plan_code
from app.products.config import format_money
from app.sales.reasoning import Reasoning

logger = get_logger(__name__)

RULE_PAYMENT_LINK = "payment_link_sent"
RULE_PAYMENT_BLOCKED = "payment_link_unavailable"


@dataclass
class Close:
    """What asking for the payment link came to.

    ``message`` is always something to send. ``order`` is present only when a
    link exists, so a caller can tell a real close from an explanation without
    reading the prose.
    """

    message: str
    order: Order | None = None

    @property
    def succeeded(self) -> bool:
        return self.order is not None


def _link_message(order: Order, *, again: bool = False) -> str:
    """The one place a payment link is written into words."""
    opening = (
        "Here it is again" if again else
        f"Here is the payment link for {order.plan_name}"
    )

    return (
        f"{opening} — "
        f"{format_money(order.amount_minor, order.currency)} per "
        f"{order.billing_period}:\n\n"
        f"{order.checkout_url}\n\n"
        "That page is Paystack's, not mine, so your card details never reach "
        "me. Nothing is charged until you complete it, and I'll set your agent "
        "up once it goes through."
    )


class ClosingService:
    """Raise the payment for whatever a conversation settled on."""

    def __init__(self, db: Session, checkout: CheckoutService | None = None):
        self.db = db
        self._checkout = checkout

    @property
    def checkout(self) -> CheckoutService:
        # Built on demand, because constructing one reads the Paystack key and
        # most turns never need a checkout at all.
        if self._checkout is None:
            self._checkout = CheckoutService(self.db)

        return self._checkout

    # ---------- what state a thread is in ----------

    def ready(self, conversation: Conversation) -> bool:
        """Whether this thread has everything needed to raise a payment.

        Deliberately strict about the stage. A buyer mid-intake has a scope but
        has not agreed to a figure, and sending them a live payment link would be
        asking for money for something they never said yes to.
        """
        if conversation.stage != STAGE_READY_TO_BUY:
            return False

        return bool(conversation.interested_plan_code and conversation.visitor_email)

    def existing_link(self, conversation: Conversation) -> Order | None:
        """A pending order on this thread that already has somewhere to pay."""
        if conversation.id is None:
            return None

        stmt = (
            select(Order)
            .where(
                Order.conversation_id == conversation.id,
                Order.status == ORDER_PENDING,
            )
            .order_by(Order.id.desc())
        )

        for order in self.db.scalars(stmt):
            if order.checkout_url:
                return order

        return None

    # ---------- the two things a caller wants ----------

    def close(self, conversation: Conversation) -> Close | None:
        """Raise a payment link if this turn is the one that earned it.

        Returns None for "nothing to say here" — a thread that is not at a
        close, or one that has already been sent its link. That is different
        from a failure, and must not put text in front of a buyer who was only
        halfway through answering questions.
        """
        if not self.ready(conversation):
            return None

        if self.existing_link(conversation) is not None:
            # Already sent. Repeating a link every turn is how a helpful agent
            # starts reading as a machine pestering someone for money.
            return None

        return self._raise_link(conversation)

    def resend(self, conversation: Conversation) -> Close | None:
        """The link this thread already has, on request.

        Separate from ``close`` because re-showing a link a buyer asked for is
        not the same act as volunteering one, and only one of the two should
        happen on its own.
        """
        existing = self.existing_link(conversation)
        if existing is not None:
            return Close(
                message=_link_message(existing, again=True), order=existing
            )

        if not self.ready(conversation):
            return None

        return self._raise_link(conversation)

    # ---------- doing it ----------

    def _raise_link(self, conversation: Conversation) -> Close:
        quote_reference = reference_from_plan_code(conversation.interested_plan_code)
        plan_code = None if quote_reference else conversation.interested_plan_code

        try:
            order = self.checkout.create_order(
                organization_id=conversation.organization_id,
                plan_code=plan_code,
                quote_reference=quote_reference,
                buyer_email=conversation.visitor_email,
                buyer_name=conversation.visitor_name,
                buyer_company=conversation.visitor_company,
                conversation=conversation,
            )
        except PaymentsNotConfigured:
            # Not the buyer's fault, and not something they can retry into
            # working. Naming what happens next is the only useful thing to say.
            logger.error(
                "Conversation %s reached a close with payments switched off",
                conversation.id,
            )
            return self._blocked(
                conversation,
                "One thing I can't do from here yet: take the payment itself. "
                "Someone will send you the link directly — I have your email "
                "and what you asked for, so you won't have to go through any "
                "of this again.",
                "payments are not configured on this deployment",
            )
        except CheckoutError as exc:
            # A quote that no longer prices, most likely. The reason is written
            # for a buyer to read, so it is passed through rather than hidden.
            logger.warning(
                "Conversation %s could not be closed: %s", conversation.id, exc
            )
            return self._blocked(
                conversation,
                f"{exc}\n\nSay the word and I'll take the four questions "
                "again — it's quicker the second time.",
                f"checkout refused: {exc}",
            )
        except PaystackError:
            logger.exception(
                "Paystack refused a checkout for conversation %s", conversation.id
            )
            return self._blocked(
                conversation,
                "Our payment provider isn't responding just now, so I couldn't "
                "raise the link. Nothing has been charged. Ask me again in a "
                "minute and I'll try again.",
                "the payment provider did not respond",
            )

        if not order.checkout_url:
            # A created order with nowhere to pay is not a close. Better to say
            # so than to send a message with a blank where the link should be.
            logger.error("Order %s has no checkout url", order.paystack_reference)
            return self._blocked(
                conversation,
                "I raised the order but the payment page didn't come back with "
                "a link. Nothing has been charged, and I've flagged it — "
                "someone will send you one directly.",
                "the provider returned no authorization url",
            )

        logger.info(
            "Conversation %s closed: order %s for %s",
            conversation.id,
            order.paystack_reference,
            conversation.visitor_email,
        )

        body = _link_message(order)

        self._record(
            conversation,
            body,
            Reasoning(
                rule=RULE_PAYMENT_LINK,
                signals=[
                    "conversation reached a price the buyer agreed to",
                    "amount re-derived by the checkout, not carried from the chat",
                    f"order {order.paystack_reference}",
                ],
            ),
        )

        return Close(message=body, order=order)

    def _blocked(
        self, conversation: Conversation, body: str, why: str
    ) -> Close:
        self._record(
            conversation,
            body,
            Reasoning(
                rule=RULE_PAYMENT_BLOCKED,
                signals=["a close was reached but no link could be raised", why],
                escalated=True,
            ),
        )

        return Close(message=body)

    def _record(
        self, conversation: Conversation, body: str, reasoning: Reasoning
    ) -> None:
        """Put what the buyer received into the thread.

        Without this the single most consequential message in a conversation —
        the one with the amount and the link — would exist only in a chat app,
        and a human reviewing the thread could not see what was sent.
        """
        if conversation.id is None:
            return

        self.db.add(
            Message(
                conversation_id=conversation.id,
                role=ROLE_AGENT,
                body=body,
                reasoning_json=reasoning.to_json(),
            )
        )
        self.db.commit()

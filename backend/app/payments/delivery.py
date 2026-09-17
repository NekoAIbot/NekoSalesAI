"""Telling the buyer, in the place they bought from.

This module exists because of a sale that worked in every respect except the
one that mattered. A buyer paid ₦148,000 on Telegram. Paystack took the money,
the order was verified, two agents were provisioned into a live workspace, and a
credentials email was queued. Then nothing was said in the Telegram thread the
buyer was sitting in, watching. From the database's point of view the sale was
complete; from the buyer's, they had paid and received silence.

The gap was structural, not a missed line of code. Provisioning ran inside a web
request that the *browser* made — the confirmation page's status poll — so
everything downstream of payment was reachable only from the surface that
happened to be open. A buyer who paid from a chat had no browser in the loop, and
nothing else was ever going to notice on their behalf.

So delivery is modelled as its own step, with its own recorded fact
(``orders.delivered_at``), driven by a reconciler that runs on a timer rather
than on a request. Two consequences worth keeping:

* **The channel is derived, not configured.** ``ChannelIdentity`` already knows
  which thread a conversation belongs to. Writing the message into the
  conversation is the whole of delivery for the web widget, which reads
  messages; Telegram and WhatsApp additionally need a push, because nobody is
  holding a connection open. One composed text, one transcript row, and a send
  only where a send is what reaching the buyer means.

* **Credentials are never put in the chat.** At the moment provisioning runs, the
  API key and temporary password exist in memory and could be pasted straight
  into the thread. They are not: a chat log is forwarded, screenshotted and
  backed up to places the buyer does not control, and a secret that has been
  posted into one cannot be unposted. Email carries them today; a short-lived
  delivery link will carry them later. The chat says where they are.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.logging import get_logger
from app.models.channel_identity import ChannelIdentity
from app.models.conversation import ROLE_AGENT, Message
from app.models.order import ORDER_PAID, ORDER_PENDING, Order
from app.models.workspace_profile import WorkspaceProfile
from app.payments.install import (
    CLOSING_LINE,
    messenger_steps,
    sign_in_url,
    website_steps,
)
from app.products.config import ROLE_SALES_AGENT, ROLE_SUPPORT_AGENT, format_money

logger = get_logger(__name__)

# The rule this message is filed under, so a transcript says why it was sent and
# a test can assert on it without depending on the copy.
RULE_DELIVERED = "workspace_delivered"

# What each agent is for, in the buyer's words rather than the schema's.
_ROLE_SUMMARY = {
    ROLE_SALES_AGENT: "answers buyers, quotes your prices and takes the sale",
    ROLE_SUPPORT_AGENT: "answers the questions you get asked over and over",
}

# The web surface reads new messages out of the conversation, so a row is
# delivery. The chat platforms need somebody to push.
_PUSH_CHANNELS = ("telegram", "whatsapp")


@dataclass(frozen=True)
class Push:
    """One outbound message waiting to be sent on a chat platform."""

    channel: str
    external_id: str
    text: str


@dataclass
class DeliveryReport:
    """What one reconcile pass did, in terms a log line can carry."""

    checked: int = 0
    newly_paid: int = 0
    provisioned: int = 0
    delivered: int = 0
    pushes: list[Push] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def quiet(self) -> bool:
        """Nothing happened, so a log line would only be noise."""
        return not (self.newly_paid or self.provisioned or self.delivered or self.errors)

    def summary(self) -> str:
        parts = [
            f"{self.checked} checked",
            f"{self.newly_paid} newly paid",
            f"{self.provisioned} provisioned",
            f"{self.delivered} delivered",
        ]

        if self.errors:
            parts.append(f"{len(self.errors)} failed")

        return ", ".join(parts)


def delivery_parts(
    order: Order,
    profiles: list[WorkspaceProfile],
    *,
    channels: tuple[str, ...] = (),
) -> list[str]:
    """The delivery, as the two or three messages it should arrive in.

    Split rather than concatenated because full install guidance runs past 4,096
    characters, which Telegram and WhatsApp both reject outright — so a single
    message would have grown until it silently stopped being delivered at all,
    and the failure would have looked like a chat platform being down.

    Splitting is also simply how this reads. "Your money arrived and here is what
    you own" is one thought; "here is how to put it on your Shopify theme" is
    another, and a customer scrolling back later wants to find the second one
    without wading through the first.
    """
    agents = tuple(
        (profile.agent_name, profile.widget_token or "")
        for profile in (_listed(profiles))
    )

    parts = [_confirmation(order, profiles)]

    website = website_steps(agents)
    if website:
        parts.append(website)

    messengers = messenger_steps(channels)
    if messengers:
        parts.append(messengers)

    # Last, so it is the line the customer's eye lands on after the instructions
    # rather than something they scrolled past three messages ago.
    parts.append(CLOSING_LINE)

    return parts


def compose_delivery(
    order: Order,
    profiles: list[WorkspaceProfile],
    *,
    channels: tuple[str, ...] = (),
) -> str:
    """The whole delivery as one text, for callers that want it in one piece.

    Pure: no database, no clock, no network. The same content goes to the web
    transcript and out over Telegram, because a buyer who paid on one channel and
    compared notes on another should not find two different accounts of what they
    now own.
    """
    return "\n\n".join(delivery_parts(order, profiles, channels=channels))


def _listed(profiles: list[WorkspaceProfile]) -> list[WorkspaceProfile]:
    """The agents worth naming: the ready ones, or all of them if none are."""
    ready = [profile for profile in profiles if profile.is_ready]

    return ready or list(profiles)


def _confirmation(order: Order, profiles: list[WorkspaceProfile]) -> str:
    """Money in, and what it turned into.

    Written to be read by someone who has just paid and is slightly nervous. It
    confirms the amount first — that is the thing they want to see — then names
    what they have, then where to sign in. It does not congratulate them.
    """
    # Through the shared formatter rather than a local f-string. The local one
    # produced "₦ 31,000" — currency code and amount joined with a space, then the
    # code swapped for a symbol, leaving the space behind. Small, and on the first
    # line of the first message a paying customer reads.
    amount = format_money(order.amount_minor, order.currency)

    lines = [
        f"Payment confirmed — {amount} for {order.plan_name}. Thank you.",
        "",
    ]

    listed = _listed(profiles)

    if listed:
        lines.append(
            "Your workspace is live"
            + (" and both agents are built:" if len(listed) > 1 else " and your agent is built:")
        )
        lines.append("")

        for profile in listed:
            summary = _ROLE_SUMMARY.get(profile.role)
            lines.append(
                f"  – {profile.agent_name}"
                + (f" — {summary}" if summary else "")
            )

        lines.append("")

    lines.append(
        f"Sign in at {sign_in_url()} with {order.buyer_email}. Your password and "
        "API key have been emailed to that address — I deliberately do not put "
        "them in chat, because a chat log gets forwarded and a key that has "
        "been posted cannot be unposted."
    )

    return "\n".join(lines)


class DeliveryService:
    """Finds sales that finished on paper and finishes them for the buyer."""

    def __init__(self, db: Session, checkout=None):
        self.db = db

        # Injectable so the whole reconcile path — including "Paystack now says
        # this was paid, and nothing told us" — is reachable in a test without an
        # account, a key or a network. That case is the entire reason this class
        # exists, so it had better be the easiest one to write a test for.
        self._checkout = checkout

    # ---------- the one that runs on a timer ----------

    def reconcile(self, *, verify_pending: bool = True) -> DeliveryReport:
        """Catch up every paid order whose buyer has not been told.

        This is the replacement for a webhook, not a supplement to one. There is
        no public HTTPS URL on this deployment, so Paystack cannot call in; the
        only way a payment made in a chat becomes known is by asking. Polling is
        therefore the primary path and is written to be safe as one: verification
        is server-to-server, provisioning is idempotent, and delivery is guarded
        by ``delivered_at`` so a buyer is told once however many passes run.
        """
        report = DeliveryReport()

        if verify_pending:
            self._verify_pending(report)

        for order in self._undelivered_paid():
            try:
                pushes = self.deliver(order)
            except Exception as exc:  # noqa: BLE001 - one order must not stop the rest
                self.db.rollback()
                report.errors.append(f"{order.paystack_reference}: {type(exc).__name__}: {exc}")
                logger.exception("Could not deliver order %s", order.paystack_reference)
                continue

            if pushes is None:
                continue

            report.delivered += 1
            report.pushes.extend(pushes)

        return report

    # ---------- one order ----------

    def deliver(self, order: Order) -> list[Push] | None:
        """Tell this buyer. Returns the sends the caller still owes, or None.

        None means there was nothing to do — unpaid, already delivered, or not
        provisioned yet — and is distinct from an empty list, which means the
        buyer has been told and no chat push is needed because they bought on the
        web and the transcript row is the delivery.
        """
        if not order.is_paid or order.is_delivered:
            return None

        profiles = self.profiles_for(order)

        if not profiles:
            # Paid but nothing stood up yet. Saying "your workspace is live"
            # here would be the same class of lie as the spinner that started
            # all this, so it waits for the next pass.
            return None

        parts = delivery_parts(order, profiles, channels=self.channels_for(order))

        pushes: list[Push] = []

        if order.conversation_id is not None:
            for index, part in enumerate(parts):
                self.db.add(
                    Message(
                        conversation_id=order.conversation_id,
                        role=ROLE_AGENT,
                        body=part,
                        # Every part carries the rule, so the transcript reads as
                        # one delivery rather than as a confirmation followed by
                        # three messages nothing accounts for.
                        reasoning_json=(
                            '{"rule": "' + RULE_DELIVERED + '", '
                            '"signals": ["payment confirmed", "workspace provisioned", '
                            '"part ' + str(index + 1) + ' of ' + str(len(parts)) + '"], '
                            '"grounded_in": ["order:' + order.paystack_reference + '"], '
                            '"escalated": false}'
                        ),
                    )
                )

            recipients = [
                identity
                for identity in self._identities(order.conversation_id)
                if identity.channel in _PUSH_CHANNELS
            ]

            # One push per part per recipient, in order. Concatenating them would
            # exceed the 4,096-character limit both chat platforms enforce, and a
            # rejected send is a buyer who paid and heard nothing — the exact
            # failure this module was written for.
            pushes = [
                Push(
                    channel=identity.channel,
                    external_id=identity.external_id,
                    text=part,
                )
                for identity in recipients
                for part in parts
            ]

        # Stamped in the same transaction as the transcript rows. If the commit
        # fails, all of them are gone and the next pass tries again; if it
        # succeeds, no later pass can send a second copy.
        order.delivered_at = datetime.now(timezone.utc)

        self.db.commit()

        return pushes

    def channels_for(self, order: Order) -> tuple[str, ...]:
        """Which channels this order paid for.

        Read back from the quote's stored requirement rather than from anything on
        the order, because the order records what was charged and the requirement
        records what was asked for. A buyer who paid the ₦4,000 Telegram add-on
        should be told about Telegram, and the only place that fact survives is
        the JSON the checkout re-priced from.

        Never raises. This decides which paragraphs a message contains; a quote
        that cannot be read is a reason to say less, not a reason to fail a
        delivery that is otherwise complete.
        """
        from app.models.quote import Quote
        from app.pricing.quotes import reference_from_plan_code, requirement_from_json

        reference = reference_from_plan_code(order.plan_code)

        if reference is None:
            return ()

        try:
            quote = self.db.execute(
                select(Quote).where(Quote.reference == reference)
            ).scalar_one_or_none()

            if quote is None:
                return ()

            return tuple(requirement_from_json(quote.requirement_json).channels)
        except Exception:
            logger.exception(
                "Could not read the channels on order %s; delivering without them",
                order.paystack_reference,
            )
            return ()

    def profiles_for(self, order: Order) -> list[WorkspaceProfile]:
        return list(
            self.db.execute(
                select(WorkspaceProfile)
                .where(WorkspaceProfile.order_id == order.id)
                .order_by(WorkspaceProfile.id)
            ).scalars().all()
        )

    # ---------- finding work ----------

    def _undelivered_paid(self) -> list[Order]:
        return list(
            self.db.execute(
                select(Order)
                .where(Order.status == ORDER_PAID, Order.delivered_at.is_(None))
                .order_by(Order.id)
            ).scalars().all()
        )

    def _pending_with_a_checkout(self) -> list[Order]:
        """Orders that were sent to Paystack and have not come back paid.

        Bounded by having a checkout URL rather than by age: an order with no URL
        was never payable, and an old one that was is still worth asking about —
        Paystack will answer "abandoned" cheaply, and the alternative is deciding
        on the buyer's behalf that they took too long.
        """
        return list(
            self.db.execute(
                select(Order)
                .where(
                    Order.status == ORDER_PENDING,
                    Order.checkout_url.is_not(None),
                )
                .order_by(Order.id.desc())
            ).scalars().all()
        )

    def _verify_pending(self, report: DeliveryReport) -> None:
        """Ask Paystack about every open order, then stand up whatever it paid for."""
        from app.payments import PaymentsNotConfigured, PaystackError
        from app.payments.checkout import CheckoutService
        from app.payments.provisioning import ProvisioningService

        checkout = self._checkout or CheckoutService(self.db)

        for order in self._pending_with_a_checkout():
            reference = order.paystack_reference
            report.checked += 1

            try:
                confirmed = checkout.confirm_by_reference(reference)
            except PaymentsNotConfigured:
                # No key in this deployment. Nothing to reconcile against, and
                # saying so once per order would fill the log.
                return
            except PaystackError as exc:
                report.errors.append(f"{reference}: {exc}")
                continue
            except Exception as exc:  # noqa: BLE001
                self.db.rollback()
                report.errors.append(f"{reference}: {type(exc).__name__}: {exc}")
                logger.exception("Verifying order %s failed", reference)
                continue

            if confirmed is None or not confirmed.is_paid:
                continue

            report.newly_paid += 1
            logger.info("Order %s came back paid; provisioning.", reference)

            try:
                result = ProvisioningService(self.db).provision(confirmed)
            except Exception as exc:  # noqa: BLE001
                self.db.rollback()
                report.errors.append(f"{reference}: provisioning {type(exc).__name__}: {exc}")
                logger.exception("Provisioning order %s failed", reference)
                continue

            if result.created:
                report.provisioned += 1

            if result.profiles:
                self._schedule_follow_ups(result.profiles[0].profile, confirmed)

    def _schedule_follow_ups(self, profile, order: Order) -> None:
        """Best-effort, exactly as on the web path.

        A scheduling problem is the seller's to fix. It must not stop the buyer
        being told their workspace is live, which is the entire point of this
        module.
        """
        from app.followups.service import FollowUpService

        try:
            FollowUpService(self.db).schedule_for(profile, order)
        except Exception:
            logger.exception(
                "Could not schedule follow-ups for order %s", order.paystack_reference
            )

    def _identities(self, conversation_id: int) -> list[ChannelIdentity]:
        return list(
            self.db.execute(
                select(ChannelIdentity).where(
                    ChannelIdentity.conversation_id == conversation_id
                )
            ).scalars().all()
        )


class DeliveryPusher:
    """Puts a delivery message onto a chat platform.

    Separate from ``DeliveryService`` because it is the one part that touches the
    network, and shared by both callers because the alternative was worse than a
    little indirection: whoever stamps ``delivered_at`` owes the send, and a
    surface that stamped it without a way to push would silently strand exactly
    the buyer this module was written for — someone who bought on Telegram and
    happened to pay with a browser open.

    Every failure is logged and swallowed. The transcript row is already written
    and the credentials email is the durable copy, so a failed push costs the
    buyer a notification, not the thing they bought.
    """

    def __init__(self, clients: dict | None = None) -> None:
        if clients is not None:
            self._clients = clients
            return

        from app.messaging.clients import TelegramClient, WhatsAppClient

        self._clients = {
            "telegram": TelegramClient(),
            "whatsapp": WhatsAppClient(),
        }

    def send_all(self, pushes: list[Push]) -> int:
        return sum(1 for push in pushes if self.send(push))

    def send(self, push: Push) -> bool:
        from app.messaging.clients import MessagingNotConfigured

        client = self._clients.get(push.channel)

        if client is None:
            logger.warning(
                "Order delivery has nowhere to go: no client for %s", push.channel
            )
            return False

        try:
            client.send_message(push.external_id, push.text)
        except MessagingNotConfigured:
            logger.warning(
                "Cannot tell buyer on %s: that channel has no credential here.",
                push.channel,
            )
            return False
        except Exception:
            logger.exception(
                "Delivering to %s %s failed", push.channel, push.external_id
            )
            return False

        logger.info("Told buyer on %s that their workspace is live.", push.channel)

        return True

"""The nudge: one polite message when a buyer started paying and stopped.

An order that went to Paystack and came back ``abandoned`` leaves a real person
halfway through paying. The sales agent would follow up if it were awake; the
reconciler is the closest thing to awake this deployment has, so it carries the
nudge.

The rules, in order of importance:

* **Once.** The dedupe is evidence, not a flag: the message is written into the
  conversation transcript when it is sent, and a candidate order is only a
  candidate while no agent message postdates the order. A crash after sending
  but before any bookkeeping costs the buyer a second nudge, never a third,
  because the second pass writes its row too.
* **On the channel they used.** The conversation's own identities decide where
  this goes, exactly as delivery does. A widget buyer gets a transcript row the
  widget shows on next load; a Telegram buyer gets a push.
* **Quiet by default.** One hour before the first nudge, and nothing at all
  after seven days: a month-old checkout is a decision, not an interruption.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config.logging import get_logger
from app.models.channel_identity import ChannelIdentity
from app.models.conversation import Conversation, Message, ROLE_AGENT
from app.models.order import ORDER_PENDING, Order

logger = get_logger(__name__)

RULE_ABANDONED = "abandoned_checkout_followup"

# How long after checkout opens before the nudge is allowed to speak.
FOLLOW_UP_AFTER = timedelta(hours=1)

# How long after checkout opens before the nudge gives up entirely.
FOLLOW_UP_WINDOW = timedelta(days=7)

_BODY = (
    "Quick one, {name} — you started the {plan} checkout a bit ago and it "
    "didn't go through. The link still works if you want to pick it up: "
    "{url}\n\nIf something got in the way, tell me here and I'll sort it."
)


def _nudge_body(order: Order) -> str:
    name = order.buyer_name or order.buyer_company or ""
    greeting = f"{name}, " if name else ""
    return _BODY.format(
        name=greeting.rstrip(", "),
        plan=order.plan_name,
        url=order.checkout_url,
    )


class RecoveryService:
    """Finds half-finished checkouts and speaks once, on the buyer's channel."""

    def __init__(self, db, pusher=None):
        self.db = db
        self._pusher = pusher

    def candidates(self) -> list[Order]:
        now = datetime.now(timezone.utc)
        found: list[Order] = []

        orders = list(
            self.db.execute(
                select(Order)
                .where(
                    Order.status == ORDER_PENDING,
                    Order.checkout_url.is_not(None),
                    Order.conversation_id.is_not(None),
                    Order.created_at < now - FOLLOW_UP_AFTER,
                    Order.created_at > now - FOLLOW_UP_WINDOW,
                )
                .order_by(Order.id.desc())
                .limit(25)
            ).scalars().all()
        )

        for order in orders:
            # Evidence dedupe: any agent message written after this order was
            # created means the nudge (or the agent itself) already spoke.
            spoken = self.db.execute(
                select(Message.id)
                .where(
                    Message.conversation_id == order.conversation_id,
                    Message.role == ROLE_AGENT,
                    Message.created_at > order.created_at,
                )
                .limit(1)
            ).scalar_one_or_none()
            if spoken is not None:
                continue

            conversation = self.db.get(Conversation, order.conversation_id)
            if conversation is None or conversation.is_handed_off:
                continue

            found.append(order)

        return found

    def run(self) -> int:
        """Nudge every candidate. Returns how many were written."""
        from app.payments.delivery import DeliveryPusher, Push, _PUSH_CHANNELS  # noqa: F401

        orders = self.candidates()
        if not orders:
            return 0

        pusher = self._pusher or DeliveryPusher()
        sent = 0

        for order in orders:
            body = _nudge_body(order)
            self.db.add(
                Message(
                    conversation_id=order.conversation_id,
                    role=ROLE_AGENT,
                    body=body,
                    reasoning_json=(
                        '{"rule": "' + RULE_ABANDONED + '", '
                        '"signals": ["checkout opened over an hour ago, unpaid"], '
                        '"grounded_in": ["order:' + order.paystack_reference + '"], '
                        '"escalated": false}'
                    ),
                )
            )

            pushes = [
                Push(
                    channel=identity.channel,
                    external_id=identity.external_id,
                    text=body,
                )
                for identity in (
                    self.db.execute(
                        select(ChannelIdentity).where(  # noqa: F821
                            ChannelIdentity.conversation_id
                            == order.conversation_id
                        )
                    ).scalars().all()
                )
                if identity.channel in _PUSH_CHANNELS
            ]

            # One transaction per order: a failure here costs one nudge, never
            # the batch, and the transcript row is the dedupe.
            try:
                self.db.commit()
            except Exception:  # noqa: BLE001
                self.db.rollback()
                logger.exception(
                    "Could not record abandoned-checkout nudge for order %s",
                    order.paystack_reference,
                )
                continue

            sent += 1
            pusher.send_all(pushes)
            logger.info(
                "Nudged buyer of order %s about an unpaid checkout.",
                order.paystack_reference,
            )

        return sent

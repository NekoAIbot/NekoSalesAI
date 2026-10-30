"""The abandoned-checkout nudge: once, on the buyer's channel, then never again."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.channel_identity import ChannelIdentity
from app.models.conversation import Conversation, Message, ROLE_AGENT
from app.models.order import ORDER_PENDING, Order
from app.payments.recovery import RecoveryService


@pytest.fixture
def make_order(db, organization):
    def _make(age_hours=2.0, paid=False, with_telegram=True):
        from datetime import datetime, timezone as tz

        org = organization
        conversation = Conversation(
            organization_id=org.id,
            public_token=f"tok_{age_hours}_{with_telegram}",
            stage="ready_to_buy",
        )
        db.add(conversation)
        db.flush()

        if with_telegram:
            db.add(
                ChannelIdentity(
                    organization_id=org.id,
                    channel="telegram",
                    external_id=f"chat_{conversation.public_token}",
                    conversation_id=conversation.id,
                )
            )

        order = Order(
            organization_id=org.id,
            conversation_id=conversation.id,
            plan_code="workforce_agent",
            plan_name="Workforce",
            billing_period="monthly",
            amount_minor=348_000_00,
            currency="NGN",
            buyer_email="buyer@example.com",
            status=ORDER_PENDING,
            paystack_reference=f"ref_{age_hours}_{with_telegram}",
            checkout_url="https://checkout.paystack.com/example",
        )
        db.add(order)
        db.flush()
        order.created_at = datetime.now(tz.utc) - timedelta(hours=age_hours)
        db.commit()
        return order

    return _make


class _SpyPusher:
    def __init__(self):
        self.pushes = []

    def send_all(self, pushes):
        self.pushes.extend(pushes)
        return len(pushes)


def test_nudges_once_then_never_again(db, make_order):
    order = make_order(age_hours=2.0)
    spy = _SpyPusher()
    service = RecoveryService(db, pusher=spy)

    assert service.run() == 1
    assert len(spy.pushes) == 1
    assert spy.pushes[0].channel == "telegram"
    assert order.checkout_url in spy.pushes[0].text

    # The transcript row is the dedupe: a second pass must stay silent.
    assert service.run() == 0
    assert len(spy.pushes) == 1


def test_young_and_stale_orders_are_left_alone(db, make_order):
    make_order(age_hours=0.2)   # too fresh
    make_order(age_hours=24 * 30)  # a decision, not an interruption
    assert RecoveryService(db, pusher=_SpyPusher()).run() == 0


def test_no_channel_no_nudge(db, make_order):
    make_order(age_hours=2.0, with_telegram=False)
    # A widget conversation still gets the transcript row (the widget shows it),
    # but nothing is pushed; counted as spoken either way.
    assert RecoveryService(db, pusher=_SpyPusher()).run() == 1

"""Choosing where follow-ups land.

Email is the default and cannot be switched off — it is the address the purchase
was made with, so it is the one destination always on file, and a customer who
disabled everything would have silently opted out of their own onboarding.
Telegram and WhatsApp are optional, independent, and may both be on at once.

The two properties worth defending here:

*Ticked is not reachable.* A customer can select WhatsApp before supplying a
number. A dispatcher trusting the tick would report a delivery that never
happened.

*Partial success is success.* If email lands and WhatsApp fails, the customer has
been told what they needed to know. Holding the follow-up scheduled would re-send
the email on the next run.
"""

import pytest

from app.followups.dispatcher import FollowUpDispatcher
from app.followups.service import Delivery, FollowUpSendError
from app.mail import MemoryMailTransport, set_transport
from app.messaging import MessagingError, MessagingNotConfigured
from app.models.workspace_profile import (
    CHANNEL_EMAIL,
    CHANNEL_TELEGRAM,
    CHANNEL_WHATSAPP,
    PROVISION_READY,
    WorkspaceProfile,
)


def profile(channels, telegram=None, whatsapp=None):
    return WorkspaceProfile(
        organization_id=1,
        plan_code="starter",
        role="sales_agent",
        status=PROVISION_READY,
        agent_name="Nera",
        company_name="Bright Dental",
        greeting="Hi",
        follow_up_channels=channels,
        telegram_chat_id=telegram,
        whatsapp_number=whatsapp,
    )


class FakeChannel:
    """Stands in for a Telegram or WhatsApp client."""

    def __init__(self, error=None):
        self.sent = []
        self.error = error

    def send_message(self, destination, text):
        if self.error is not None:
            raise self.error
        self.sent.append((destination, text))


@pytest.fixture
def outbox():
    transport = MemoryMailTransport()
    set_transport(transport)

    yield transport

    set_transport(None)


DELIVERY = Delivery(to_email="owner@bright.example", subject="Subject", body="Body")


# ---------- what the customer chose ----------


def test_email_is_the_default():
    assert profile("email").chosen_channels == (CHANNEL_EMAIL,)


def test_all_three_can_be_on_at_once():
    chosen = profile("email,telegram,whatsapp", "555", "+2348").chosen_channels

    assert chosen == (CHANNEL_EMAIL, CHANNEL_TELEGRAM, CHANNEL_WHATSAPP)


@pytest.mark.parametrize("stored", ["telegram", "", "whatsapp,telegram"])
def test_email_is_added_back_when_missing(stored):
    """A workspace must never be unreachable, however the row was written."""
    assert CHANNEL_EMAIL in profile(stored, "555", "+2348").chosen_channels


def test_an_unknown_channel_is_dropped():
    """A stale row must not name a channel this release cannot deliver on."""
    assert profile("email,carrier_pigeon").chosen_channels == (CHANNEL_EMAIL,)


def test_a_channel_with_no_destination_is_not_reachable():
    """Chosen and reachable are different facts."""
    chosen = profile("email,whatsapp")

    assert CHANNEL_WHATSAPP in chosen.chosen_channels
    assert CHANNEL_WHATSAPP not in chosen.reachable_channels


# ---------- dispatch ----------


def test_every_reachable_channel_receives_the_follow_up(outbox):
    telegram, whatsapp = FakeChannel(), FakeChannel()

    FollowUpDispatcher(
        profile("email,telegram,whatsapp", "555", "+2348"), telegram, whatsapp
    ).send(DELIVERY)

    assert len(outbox.outbox) == 1
    assert len(telegram.sent) == 1
    assert len(whatsapp.sent) == 1


def test_the_subject_survives_on_a_channel_with_no_subject_line(outbox):
    """Telegram and WhatsApp have no subject field, and the copy was written
    around that one-line summary."""
    telegram = FakeChannel()

    FollowUpDispatcher(profile("email,telegram", "555"), telegram, FakeChannel()).send(
        DELIVERY
    )

    assert telegram.sent[0][1].startswith("Subject")
    assert "Body" in telegram.sent[0][1]


def test_a_channel_that_was_not_chosen_is_left_alone(outbox):
    telegram = FakeChannel()

    FollowUpDispatcher(profile("email", "555"), telegram, FakeChannel()).send(DELIVERY)

    assert telegram.sent == []
    assert len(outbox.outbox) == 1


def test_one_failing_channel_does_not_hold_back_the_others(outbox):
    """Partial success is success: raising here would re-send the email."""
    telegram = FakeChannel(error=MessagingError("telegram down"))
    whatsapp = FakeChannel()

    dispatcher = FollowUpDispatcher(
        profile("email,telegram,whatsapp", "555", "+2348"), telegram, whatsapp
    )
    dispatcher.send(DELIVERY)

    assert len(outbox.outbox) == 1
    assert len(whatsapp.sent) == 1

    failed = [o for o in dispatcher.outcomes if not o.sent]
    assert [o.channel for o in failed] == [CHANNEL_TELEGRAM]


def test_an_unconfigured_channel_is_reported_not_fatal(outbox):
    """No credentials for a channel is the deployment's gap, not a broken send."""
    telegram = FakeChannel(error=MessagingNotConfigured("no token"))

    dispatcher = FollowUpDispatcher(
        profile("email,telegram", "555"), telegram, FakeChannel()
    )
    dispatcher.send(DELIVERY)

    assert len(outbox.outbox) == 1
    telegram_outcome = next(
        o for o in dispatcher.outcomes if o.channel == CHANNEL_TELEGRAM
    )
    assert telegram_outcome.sent is False
    assert "not configured" in telegram_outcome.error


def test_when_every_channel_fails_the_follow_up_stays_retryable():
    """Raising is what leaves the row scheduled for the next run."""

    class Broken(MemoryMailTransport):
        name = "broken"

        def _deliver(self, message):
            raise RuntimeError("mail down")

    set_transport(Broken())
    try:
        dispatcher = FollowUpDispatcher(
            profile("email,telegram", "555"),
            FakeChannel(error=MessagingError("telegram down")),
            FakeChannel(),
        )

        with pytest.raises(FollowUpSendError):
            dispatcher.send(DELIVERY)
    finally:
        set_transport(None)


def test_a_raising_channel_client_does_not_stop_the_run(outbox):
    """An unexpected exception from one client is contained."""
    telegram = FakeChannel(error=ValueError("something odd"))

    dispatcher = FollowUpDispatcher(
        profile("email,telegram", "555"), telegram, FakeChannel()
    )
    dispatcher.send(DELIVERY)

    assert len(outbox.outbox) == 1
    assert any(not o.sent for o in dispatcher.outcomes)

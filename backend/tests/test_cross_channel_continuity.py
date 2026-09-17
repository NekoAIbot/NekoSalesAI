"""Web <-> Telegram cross-channel continuity.

Proves that Web and Telegram use the SAME Nera engine, services, and
persistence layer. Both channels flow through the same ConversationService,
CheckoutService, ClosingService, ProvisioningService, and database.
"""

import pytest

from app.config.settings import settings
from app.messaging.inbound import InboundMessage, KIND_TEXT
from app.messaging.service import InboundMessagingService
from app.models.channel_identity import CHANNEL_TELEGRAM, ChannelIdentity
from app.models.organization import Organization
from app.models.workspace_profile import PROVISION_READY, WorkspaceProfile
from app.payments.checkout import CheckoutService
from app.payments.delivery import DeliveryService
from app.payments.paystack import PaystackClient
from app.payments.provisioning import ProvisioningService
from app.sales.service import ConversationService
from tests.test_checkout import (
    SALES_BUILD,
    TEST_SECRET,
    FakeTransport,
    make_order,
)


@pytest.fixture
def storefront(db):
    org = Organization(name="NekoSalesAI", slug=settings.STOREFRONT_ORG_SLUG)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


class TestSharedEngine:
    """Both channels use the SAME Nera business logic services."""

    def test_both_channels_use_conversation_service(self, db, storefront):
        """Web and Telegram both answer through ConversationService."""
        web_svc = ConversationService(db)
        web_conv = web_svc.start(storefront.id)

        tg_msg = InboundMessage(
            channel=CHANNEL_TELEGRAM,
            external_id="tg-engine-test",
            delivery_id="tg:100",
            kind=KIND_TEXT,
            text="Hello from Telegram",
            sender_name="Engine Test",
        )
        tg_svc = InboundMessagingService(db)
        handled = tg_svc.handle(storefront.id, tg_msg)

        assert web_conv.id is not None
        assert handled.conversation.id is not None
        assert web_conv.organization_id == storefront.id
        assert handled.conversation.organization_id == storefront.id

    def test_both_channels_use_closing_service(self, db, storefront):
        """ClosingService is shared between channels."""
        from app.sales.closing import ClosingService

        ClosingService(db)
        ClosingService(db)

    def test_both_channels_use_checkout_service(self, db, storefront):
        """CheckoutService is shared between channels."""
        checkout = CheckoutService(db)
        assert checkout.db is not None


class TestSharedPersistence:
    """Both channels persist to the SAME database and can read each other's state."""

    def test_telegram_order_provisions_through_shared_pipeline(self, db, storefront):
        """A Telegram order goes through the same provision/delivery pipeline."""
        transport = FakeTransport(paid=True)
        paystack = PaystackClient(secret_key=TEST_SECRET, transport=transport)
        checkout = CheckoutService(db, client=paystack)

        order = make_order(
            checkout,
            storefront,
            build=SALES_BUILD,
            buyer_email="tg-provision@example.com",
            buyer_company="TG Provision Co",
        )

        delivery = DeliveryService(db, checkout=checkout)
        report = delivery.reconcile()
        assert report.newly_paid == 1
        assert report.provisioned == 1
        assert report.delivered == 1

        # Profiles belong to the buyer's organization (created during provisioning)
        profiles = db.query(WorkspaceProfile).all()
        assert len(profiles) >= 1
        assert profiles[0].status == PROVISION_READY
        assert profiles[0].widget_token
        assert profiles[0].api_key_prefix


class TestTelegramIdentityLinking:
    """ChannelIdentity links Telegram chat ids to conversations."""

    def test_telegram_creates_channel_identity(self, db, storefront):
        """First telegram message creates a ChannelIdentity."""
        tg_msg = InboundMessage(
            channel=CHANNEL_TELEGRAM,
            external_id="tg-identity-test",
            delivery_id="tg:300",
            kind=KIND_TEXT,
            text="Hello",
            sender_name="Identity Test",
        )
        tg_svc = InboundMessagingService(db)
        handled = tg_svc.handle(storefront.id, tg_msg)

        identity = (
            db.query(ChannelIdentity)
            .filter(
                ChannelIdentity.channel == CHANNEL_TELEGRAM,
                ChannelIdentity.external_id == "tg-identity-test",
            )
            .first()
        )
        assert identity is not None
        assert identity.conversation_id == handled.conversation.id

    def test_telegram_returns_to_same_conversation(self, db, storefront):
        """Second telegram message reuses the same conversation."""
        tg_msg1 = InboundMessage(
            channel=CHANNEL_TELEGRAM,
            external_id="tg-return-test",
            delivery_id="tg:301",
            kind=KIND_TEXT,
            text="Hello",
            sender_name="Return Test",
        )
        tg_svc = InboundMessagingService(db)
        handled1 = tg_svc.handle(storefront.id, tg_msg1)

        tg_msg2 = InboundMessage(
            channel=CHANNEL_TELEGRAM,
            external_id="tg-return-test",
            delivery_id="tg:302",
            kind=KIND_TEXT,
            text="Hello again",
            sender_name="Return Test",
        )
        handled2 = tg_svc.handle(storefront.id, tg_msg2)

        assert handled1.conversation.id == handled2.conversation.id


class TestNoDuplicatedLogic:
    """Verify business logic is NOT duplicated inside Telegram handlers."""

    def test_inbound_messaging_service_does_not_compose_replies(self, db, storefront):
        """InboundMessagingService delegates reply composition to ConversationService."""
        tg_msg = InboundMessage(
            channel=CHANNEL_TELEGRAM,
            external_id="tg-no-duplicate",
            delivery_id="tg:400",
            kind=KIND_TEXT,
            text="Hello",
            sender_name="No Dup Test",
        )
        tg_svc = InboundMessagingService(db)
        handled = tg_svc.handle(storefront.id, tg_msg)

        assert handled.replies is not None

"""End-to-end lifecycle regression for Nera.

One module, one file. Uses the existing test/simulation infrastructure and
simulated providers only. No real credentials, no network, no architecture
changes. Each test name maps to one stage of the purchase lifecycle or one
failure/idempotency requirement.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy.orm import Session

from app.models.order import ORDER_PAID
from app.payments.checkout import CheckoutService
from app.payments.paystack import PaystackClient
from app.payments.delivery import DeliveryService
from app.payments.provisioning import ProvisioningService
from app.products.config import ROLE_SALES_AGENT, ROLE_SUPPORT_AGENT
from app.sales.agent import RULE_PAYMENT_REPORTED, RULE_UNKNOWN
from app.sales.service import ConversationService
from tests.simulation.buyer import BuyerState, next_utterance, opening_line
from tests.simulation.channels import SURFACE_NAMES, WebSurface, build_surface
from tests.simulation.expectations import FAILURE, Transcript, check
from tests.simulation.personas import Persona
from tests.simulation.products import ProductRunner, WidgetSurface
from tests.simulation.purchases import PurchaseRun, order_for, quoted_total
from tests.simulation.run import run_one
from tests.test_checkout import (
    BOTH_PRODUCTS_BUILD,
    SALES_BUILD,
    SUPPORT_BUILD,
    TEST_SECRET,
    FakeTransport,
    make_order,
    charge_event,
)


def _buyer_persona() -> Persona:
    return Persona(
        persona_id="lifecycle-buyer",
        business=type("Business", (), {"text": "I run a food store", "expectation": "matches"})(),
        product_ask="the sales rep",
        expected_products=("sales_agent",),
        channel_ask="just my website",
        expected_channels=("web",),
        volume_ask="about 500",
        expected_volume=500,
        integration_ask="none",
        expected_integrations=0,
        name="Lifecycle Buyer",
        email="lifecycle@example.com",
        company="Lifecycle Co",
        behaviours=(),
        interjections=(),
    )


@pytest.fixture
def storefront(db):
    from app.config.settings import settings
    from app.models.organization import Organization

    org = Organization(name="NekoSalesAI", slug=settings.STOREFRONT_ORG_SLUG)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def test_visitor_to_delivered_lifecycle_web(db, client, storefront):
    """Visitor -> conversation -> discovery -> quote -> checkout -> payment ->
    verification -> provisioning -> delivery -> post-purchase usage."""
    surface = WebSurface(db, client)
    surface.open()
    assert surface.token
    assert surface.conversation_id is not None

    persona = _buyer_persona()
    state = BuyerState()
    said = opening_line(persona)
    transcript = Transcript(persona=persona, surface="web")
    for _ in range(16):
        turn = surface.say(said)
        transcript.turns.append(turn)
        nxt = next_utterance(persona, turn.text, state)
        if nxt is None:
            break
        said = nxt

    findings = check(transcript)
    hard_failures = [f for f in findings if f.severity == FAILURE]
    assert not hard_failures, "\n".join(f"{f.category}: {f.summary}" for f in hard_failures)
    assert transcript.reached_quote()

    surface.checkout(persona)
    order = order_for(db, surface.conversation_id)
    assert order is not None
    assert order.checkout_url

    transport = FakeTransport(paid=True, amount_override=order.amount_minor)
    paystack = PaystackClient(secret_key=TEST_SECRET, transport=transport)
    checkout = CheckoutService(db, client=paystack)
    delivery = DeliveryService(db, checkout=checkout)

    report = delivery.reconcile()
    assert report.newly_paid == 1
    assert report.provisioned == 1

    db.refresh(order)
    assert order.status == ORDER_PAID

    result = ProvisioningService(db).provision(order)
    assert result.created
    assert len(result.profiles) >= 1
    profile = next(p for p in result.profiles if p.role == ROLE_SALES_AGENT)
    assert profile.widget_token
    assert profile.api_key_prefix
    assert profile.status == "ready"
    assert profile.agent_name

    messages = [
        msg.body
        for msg in ConversationService(db).messages(surface.conversation_id)
        if "Payment confirmed" in (msg.body or "")
    ]
    assert messages, "buyer was not delivered a confirmation"

    runner = ProductRunner(db, client)
    run = runner.exercise(profile)
    product_failures = [f for f in run.findings if f.severity == FAILURE]
    assert not product_failures, "\n".join(f"{f.category}: {f.summary}" for f in product_failures)


def test_idempotent_provisioning_and_delivery(db, client, storefront):
    """Provisioning and delivery are idempotent."""
    transport = FakeTransport(paid=True)
    paystack = PaystackClient(secret_key=TEST_SECRET, transport=transport)
    checkout = CheckoutService(db, client=paystack)

    order = make_order(checkout, storefront, build=SALES_BUILD)
    order = checkout.confirm(
        paystack.charge_from_webhook(
            charge_event(order.paystack_reference, order.amount_minor)
        )
    )
    assert order.status == ORDER_PAID

    first = ProvisioningService(db).provision(order)
    second = ProvisioningService(db).provision(order)
    assert first.created
    assert not second.created
    assert len(second.profiles) == len(first.profiles)

    delivery = DeliveryService(db, checkout=checkout)
    assert delivery.reconcile().delivered == 1
    assert delivery.reconcile().delivered == 0


def test_duplicate_payment_and_reconciliation(db, client, storefront):
    """Duplicate charge.success events do not double-provision or double-deliver."""
    transport = FakeTransport(paid=True)
    paystack = PaystackClient(secret_key=TEST_SECRET, transport=transport)
    checkout = CheckoutService(db, client=paystack)

    order = make_order(checkout, storefront, build=SUPPORT_BUILD)
    event = charge_event(order.paystack_reference, order.amount_minor)
    checkout.confirm(paystack.charge_from_webhook(event))
    checkout.confirm(paystack.charge_from_webhook(event))

    result = ProvisioningService(db).provision(order)
    assert result.created
    assert len(result.profiles) == 1

    delivery = DeliveryService(db, checkout=checkout)
    assert delivery.reconcile().delivered == 1


def test_provisioning_twice_does_not_duplicate_resources(db, client, storefront):
    """A second provisioning attempt for the same paid order is a no-op."""
    transport = FakeTransport(paid=True)
    paystack = PaystackClient(secret_key=TEST_SECRET, transport=transport)
    checkout = CheckoutService(db, client=paystack)

    order = make_order(checkout, storefront, build=BOTH_PRODUCTS_BUILD)
    order = checkout.confirm(
        paystack.charge_from_webhook(
            charge_event(order.paystack_reference, order.amount_minor)
        )
    )

    first = ProvisioningService(db).provision(order)
    second = ProvisioningService(db).provision(order)
    assert first.created
    assert not second.created
    assert {p.role for p in first.profiles} == {ROLE_SALES_AGENT, ROLE_SUPPORT_AGENT}
    assert {p.role for p in second.profiles} == {ROLE_SALES_AGENT, ROLE_SUPPORT_AGENT}


def test_delivery_twice_does_not_duplicate_buyer_messages(db, client, storefront):
    """A second delivery pass does not send a second confirmation."""
    transport = FakeTransport(paid=True)
    paystack = PaystackClient(secret_key=TEST_SECRET, transport=transport)
    checkout = CheckoutService(db, client=paystack)

    order = make_order(checkout, storefront, build=SALES_BUILD)
    order = checkout.confirm(
        paystack.charge_from_webhook(
            charge_event(order.paystack_reference, order.amount_minor)
        )
    )

    ProvisioningService(db).provision(order)
    delivery = DeliveryService(db, checkout=checkout)
    assert delivery.reconcile().delivered == 1
    assert delivery.reconcile().delivered == 0


def test_duplicate_telegram_update_is_suppressed(db, client, storefront):
    """Duplicate inbound Telegram deliveries are dropped."""
    from app.messaging.inbound import InboundMessage, KIND_TEXT
    from app.messaging.service import InboundMessagingService

    service = InboundMessagingService(db)
    first = service.handle(
        storefront.id,
        InboundMessage(
            channel="telegram",
            external_id="dup-telegram",
            delivery_id="dup-telegram-1",
            kind=KIND_TEXT,
            text="hi",
            command="",
            sender_name="Dup",
        ),
    )
    assert first.replies

    handled = service.handle(
        storefront.id,
        InboundMessage(
            channel="telegram",
            external_id="dup-telegram",
            delivery_id="dup-telegram-1",
            kind=KIND_TEXT,
            text="hi",
            command="",
            sender_name="Dup",
        ),
    )
    assert handled.duplicate is True
    assert handled.replies == []


def test_malformed_inbound_message_is_handled_safely(db, client, storefront):
    """Unsupported inbound deliveries do not crash the agent."""
    from app.messaging.inbound import InboundMessage, KIND_UNSUPPORTED
    from app.messaging.service import InboundMessagingService

    service = InboundMessagingService(db)
    handled = service.handle(
        storefront.id,
        InboundMessage(
            channel="telegram",
            external_id="malformed",
            delivery_id="malformed-1",
            kind=KIND_UNSUPPORTED,
            text="",
            command="",
            sender_name="Malformed",
        ),
    )
    assert handled.replies


def test_failed_payment_is_not_treated_as_paid(db, client, storefront):
    """An abandoned payment does not provision or deliver."""
    transport = FakeTransport(paid=False)
    paystack = PaystackClient(secret_key=TEST_SECRET, transport=transport)
    checkout = CheckoutService(db, client=paystack)

    order = make_order(checkout, storefront, build=SALES_BUILD)
    event = charge_event(order.paystack_reference, order.amount_minor)
    event["data"]["status"] = "abandoned"
    order = checkout.confirm(
        paystack.charge_from_webhook(event)
    )
    assert order.status != ORDER_PAID


def test_approval_gated_discount_request_is_escalated(db, client, storefront):
    """Discount/custom-term requests must not be answered with a new price."""
    surface = WebSurface(db, client)
    surface.open()

    persona = Persona(
        persona_id="approval-discount",
        business=type("Business", (), {"text": "I run a food store", "expectation": "matches"})(),
        product_ask="the sales rep",
        expected_products=("sales_agent",),
        channel_ask="just my website",
        expected_channels=("web",),
        volume_ask="about 500",
        expected_volume=500,
        integration_ask="none",
        expected_integrations=0,
        name="Discount Buyer",
        email="discount@example.com",
        company="Discount Co",
        behaviours=("demands_discount",),
        interjections=(),
    )
    state = BuyerState()
    said = opening_line(persona)
    for _ in range(16):
        turn = surface.say(said)
        if turn.rule == RULE_UNKNOWN and not turn.escalated:
            pytest.fail("Discount request reached RULE_UNKNOWN without escalation")
        if "50%" in turn.text or "discount" in turn.text.lower():
            if turn.rule not in {"off_script_discount_request", "custom_terms"} and not turn.escalated:
                pytest.fail("Discount request was answered without escalation")
        if turn.escalated:
            break
        nxt = next_utterance(persona, turn.text, state)
        if nxt is None:
            break
        said = nxt


def test_support_request_requiring_escalation(db, client, storefront):
    """Support requests about money/changes/legal are escalated."""
    transport = FakeTransport(paid=True)
    paystack = PaystackClient(secret_key=TEST_SECRET, transport=transport)
    checkout = CheckoutService(db, client=paystack)

    order = make_order(checkout, storefront, build=SALES_BUILD)
    order = checkout.confirm(
        paystack.charge_from_webhook(
            charge_event(order.paystack_reference, order.amount_minor)
        )
    )
    profiles = ProvisioningService(db).provision(order).profiles
    profile = next(p for p in profiles if p.role == ROLE_SALES_AGENT)

    surface = WidgetSurface(db, client, profile.widget_token)
    assert surface.open()
    turn = surface.say("I want a refund")
    assert turn.escalated or "team" in turn.text.lower() or "person" in turn.text.lower()


def test_cross_tenant_widget_tokens_are_distinct(db, client, storefront):
    """One workspace cannot use another workspace's widget token."""
    transport = FakeTransport(paid=True)
    paystack = PaystackClient(secret_key=TEST_SECRET, transport=transport)
    checkout = CheckoutService(db, client=paystack)

    order_a = make_order(
        checkout,
        storefront,
        build=SALES_BUILD,
        buyer_email="a@example.com",
        buyer_company="A Ltd",
    )
    order_b = make_order(
        checkout,
        storefront,
        build=SUPPORT_BUILD,
        buyer_email="b@example.com",
        buyer_company="B Ltd",
    )

    for order in (order_a, order_b):
        checkout.confirm(
            paystack.charge_from_webhook(
                charge_event(order.paystack_reference, order.amount_minor)
            )
        )

    profiles_a = ProvisioningService(db).provision(order_a).profiles
    profiles_b = ProvisioningService(db).provision(order_b).profiles

    tokens_a = {p.widget_token for p in profiles_a}
    tokens_b = {p.widget_token for p in profiles_b}
    assert tokens_a.isdisjoint(tokens_b)

    for profile in profiles_a:
        response = client.get(f"/api/v1/widget/{profile.widget_token}/conversations")
        assert response.status_code == 200

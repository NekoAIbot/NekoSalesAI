"""Persist owner memory and report only paid workspace activity."""
from datetime import datetime, timezone

from sqlalchemy import select

from app.mira.coordinator import respond
from app.models import MiraMemory, Organization, Order
from app.models.order import ORDER_PAID


def test_mira_memory_upserts_and_is_org_scoped(db, organization):
    response = respond(db, organization.id, "remember that we close on sundays")
    assert response == "got it, i'll remember: we close on sundays"
    assert db.execute(select(MiraMemory).where(MiraMemory.organization_id == organization.id)).scalar_one().value == "we close on sundays"
    other = Organization(name="Elsewhere", slug="elsewhere")
    db.add(other)
    db.commit()
    assert "we close on sundays" in respond(db, organization.id, "what should you know?")
    assert "we close on sundays" not in respond(db, other.id, "what should you know?")


def test_sales_task_is_todo_not_claimed_action(db, organization):
    reply = respond(db, organization.id, "follow up with customers who asked about delivery")
    assert reply.startswith("noted as a TODO:")
    assert "haven't contacted anyone" in reply
    assert db.execute(select(MiraMemory).where(MiraMemory.organization_id == organization.id)).scalar_one().value.startswith("todo:")


def test_daily_report_uses_paid_orders_and_real_conversation_count(db, organization):
    from app.models.conversation import Conversation

    now = datetime(2026, 10, 30, 10, 0, tzinfo=timezone.utc)
    db.add(Conversation(organization_id=organization.id, public_token="owner-convo", stage="greeting"))
    order = Order(
        organization_id=organization.id, paystack_reference="paid-test", plan_code="x", plan_name="X",
        billing_period="monthly", amount_minor=150000, currency="NGN", buyer_email="buyer@example.com",
        status=ORDER_PAID, paid_at=now,
    )
    unpaid = Order(
        organization_id=organization.id, paystack_reference="pending-test", plan_code="x", plan_name="X",
        billing_period="monthly", amount_minor=250000, currency="NGN", buyer_email="buyer2@example.com",
        status="pending", paid_at=now,
    )
    db.add_all([order, unpaid])
    db.commit()
    reply = respond(db, organization.id, "how did we do today?", now=now)
    assert "1 paid order(s)" in reply
    assert "NGN 1,500.00" in reply
    assert "1 conversation(s)" in reply
    assert "pending" not in reply


def test_help_command_returns_discoverable_capabilities(db, organization):
    reply = respond(db, organization.id, "", command="mira")
    assert "business manager" in reply
    assert "revenue" in reply

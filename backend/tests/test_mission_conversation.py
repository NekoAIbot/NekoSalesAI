"""Regression coverage for the exact mission conversation.

The scenario, end to end: a business owner describes their business, asks
questions mid-intake, answers with exact figures, and the scope, quote and
product-question answers must all reflect what they actually said.
"""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
import app.models  # noqa: F401
from app.config.settings import settings
from app.messaging.inbound import InboundMessage, KIND_TEXT
from app.messaging.service import InboundMessagingService
from app.models.conversation import Conversation
from app.models.organization import Organization


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def storefront(db):
    org = Organization(name="NekoSalesAI", slug=settings.STOREFRONT_ORG_SLUG)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def service(db):
    return InboundMessagingService(db)


def _send(service, org, text, n):
    msg = InboundMessage(
        channel="telegram",
        external_id="4242",
        delivery_id=f"tg:{n}",
        kind=KIND_TEXT,
        text=text,
    )
    return service.handle(org.id, msg)


def _scope(db):
    conv = db.query(Conversation).one()
    return json.loads(conv.scope_json or "{}")


def test_a_product_question_mid_intake_is_answered_not_escalated(service, storefront, db):
    """"What does sales mean?" mid-intake: answered from the catalog, scope intact."""
    _send(service, storefront, "I run a clothing business", 1)
    _send(service, storefront, "Workforce", 2)

    handled = _send(service, storefront, "What does sales mean?", 3)

    joined = "\n".join(handled.replies)
    # Answered from the catalog, not handed to a team.
    assert "AI Sales Agent" in joined
    assert "pass" not in joined.lower() or "Paystack" in joined
    # The Workforce selection survived the interruption.
    assert _scope(db)["products"] == ["workforce_agent"]
    # The channels question is still on the table.
    assert "Where should it answer" in joined


def test_the_exact_mission_conversation(service, storefront, db):
    """The full scenario: describe, choose, ask, answer, configure, quote."""
    _send(service, storefront, "I run a clothing business", 1)
    _send(service, storefront, "Workforce", 2)
    _send(service, storefront, "What does sales mean?", 3)
    _send(service, storefront, "my website and whatsapp", 4)
    _send(service, storefront, "12k", 5)
    _send(service, storefront, "15", 6)
    handled = _send(service, storefront, "English, Yoruba, Hausa, Igbo, Pidgin", 7)

    scope = _scope(db)
    assert scope["products"] == ["workforce_agent"]
    assert scope["channels"] == ["web", "whatsapp"]
    # 12k is 12,000 — the exact figure, not a snapped band.
    assert scope["monthly_conversations"] == 12_000
    # 15 integrations is a count, not a scoping handoff.
    assert scope["integrations"] == 15
    # Exactly the five languages selected.
    assert set(scope["languages"]) == {"en", "yo", "ha", "ig", "pid"}

    conv = db.query(Conversation).one()
    assert conv.stage == "ready_to_buy"

    quote_text = "\n".join(handled.replies)
    # The quote reflects the actual configuration.
    assert "Workforce" in quote_text
    assert "12,000 conversations" in quote_text
    # No invented integration names.
    assert "CRM" not in quote_text
    assert "Calendar" not in quote_text
    # No "English-only" against five selected languages.
    assert "English-only" not in quote_text


def test_integration_count_is_never_invented_names(service, storefront, db):
    _send(service, storefront, "I need a sales agent", 1)
    _send(service, storefront, "just my website", 2)
    _send(service, storefront, "500", 3)
    handled = _send(service, storefront, "15", 4)

    scope = _scope(db)
    assert scope["integrations"] == 15

    # The next question is languages — the count was accepted.
    joined = "\n".join(handled.replies)
    assert "language" in joined.lower()
    # No escalation.
    assert "team" not in joined or "Paystack" in joined


def test_volume_is_the_exact_figure(service, storefront, db):
    _send(service, storefront, "sales agent", 1)
    _send(service, storefront, "web only", 2)
    _send(service, storefront, "12k", 3)

    assert _scope(db)["monthly_conversations"] == 12_000


def test_support_agent_question_is_answered(service, storefront, db):
    _send(service, storefront, "I run a clothing business", 1)
    handled = _send(service, storefront, "What can the Support Agent do?", 2)

    joined = "\n".join(handled.replies)
    assert "AI Support Agent" in joined
    assert "pass" not in joined.lower() or "Paystack" in joined


def test_workforce_order_capability_question(service, storefront, db):
    _send(service, storefront, "I run a clothing business", 1)
    handled = _send(service, storefront, "Can Workforce take orders?", 2)

    joined = "\n".join(handled.replies)
    assert "Yes" in joined
    assert "Paystack" in joined


def test_inventory_question_names_the_integration(service, storefront, db):
    _send(service, storefront, "I run a clothing business", 1)
    handled = _send(service, storefront, "Can it check inventory?", 2)

    joined = "\n".join(handled.replies)
    assert "inventory integration" in joined.lower()


def test_an_interrupt_does_not_lose_the_place(service, storefront, db):
    """Ask a question mid-intake; the pending question stays on the table."""
    _send(service, storefront, "I run a clothing business", 1)
    _send(service, storefront, "Workforce", 2)
    handled = _send(service, storefront, "What can the Support Agent do?", 3)

    joined = "\n".join(handled.replies)
    # The answer...
    assert "AI Support Agent" in joined
    # ...and the pending question, so the buyer knows where they are.
    assert "Where should it answer" in joined
    # Scope intact.
    assert _scope(db)["products"] == ["workforce_agent"]

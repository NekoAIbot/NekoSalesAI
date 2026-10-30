"""Tests for Telegram natural conversation experience.

Verifies:
- Extracting multi-step information from natural language in a single message.
- Immediate itemized quoting when all requirements are provided in one message.
- Natural acceptance of recommendations via agreement ('sounds good', 'yes', 'let's do that').
- Retaining answers across turns from conversational memory.
- Answering mid-scoping clarification questions (channels, integrations, languages, volume)
  grounded in the catalog while preserving the pending question.
- Guided selection controls attached as a fallback on Telegram.
"""

from __future__ import annotations

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
    org = Organization(name="NekoSalesAI Demo", slug=settings.STOREFRONT_ORG_SLUG)
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
        external_id="12345",
        delivery_id=f"tg_nat_{n}",
        kind=KIND_TEXT,
        text=text,
    )
    return service.handle(org.id, msg)


def _scope(db):
    conv = db.query(Conversation).one()
    return json.loads(conv.scope_json or "{}")


def test_multi_step_extraction_in_single_turn(service, storefront, db):
    """Providing product, channels, and volume in one message extracts all three."""
    handled = _send(
        service,
        storefront,
        "I need an AI sales agent for WhatsApp and my website, handling around 1,000 chats a month",
        1,
    )

    scope = _scope(db)
    assert scope["products"] == ["sales_agent"]
    assert "web" in scope["channels"] and "whatsapp" in scope["channels"]
    assert scope["monthly_conversations"] == 1_000

    reply_text = "\n".join(handled.replies)
    # Acknowledges captured details naturally
    assert "Sales Agent" in reply_text
    assert "WhatsApp" in reply_text
    # Advances directly to asking about integrations rather than re-asking channels/volume
    assert "systems does it need to talk to" in reply_text or "integrations" in reply_text.lower()


def test_complete_natural_explanation_quotes_immediately(service, storefront, db):
    """Providing all 5 requirements in one natural message yields an immediate quote."""
    handled = _send(
        service,
        storefront,
        "I want an AI sales agent on website and WhatsApp, 1,000 chats a month, no integrations, English and Pidgin",
        1,
    )

    scope = _scope(db)
    assert scope["products"] == ["sales_agent"]
    assert "web" in scope["channels"] and "whatsapp" in scope["channels"]
    assert scope["monthly_conversations"] == 1_000
    assert scope["integrations"] == 0
    assert set(scope["languages"]) == {"en", "pid"}

    conv = db.query(Conversation).one()
    assert conv.stage == "ready_to_buy"
    reply_text = "\n".join(handled.replies)
    assert "₦" in reply_text  # Quoted price present
    assert "AI Sales Agent" in reply_text


def test_recommendation_accepted_via_natural_agreement(service, storefront, db):
    """Saying 'sounds good, let's do that' accepts the recommended product."""
    # Turn 1: Describe business with selling and answering needs -> triggers recommendation
    handled1 = _send(
        service,
        storefront,
        "We run an online pharmacy. We get lots of repeated questions about drugs and we also want to take orders.",
        1,
    )
    reply1 = "\n".join(handled1.replies)
    assert "AI Sales Agent" in reply1 and "AI Support Agent" in reply1

    # Turn 2: Natural agreement
    handled2 = _send(service, storefront, "Sounds good, let's do that", 2)
    scope = _scope(db)
    assert scope["products"] == ["workforce_agent"]

    reply2 = "\n".join(handled2.replies)
    # Advances to channels question
    assert "Where should it answer" in reply2


def test_cross_turn_memory_retention(service, storefront, db):
    """Mentioning a channel in Turn 1 is retained when choosing a product in Turn 2."""
    # Turn 1: Mention customers contact via WhatsApp
    _send(service, storefront, "We sell shoes and customers mostly message us on WhatsApp. What do you build?", 1)

    # Turn 2: Select product
    handled2 = _send(service, storefront, "I need a sales agent", 2)
    scope = _scope(db)
    assert scope["products"] == ["sales_agent"]
    # Retained channels from Turn 1
    assert "whatsapp" in scope["channels"]


def test_clarification_questions_mid_scoping(service, storefront, db):
    """Asking what channels, integrations, or languages are supported answers authoritatively without losing scope."""
    _send(service, storefront, "I need an AI sales agent", 1)
    scope1 = _scope(db)
    assert scope1["products"] == ["sales_agent"]

    # Ask about channels
    handled = _send(service, storefront, "What channels do you support?", 2)
    reply = "\n".join(handled.replies)
    assert "WhatsApp" in reply
    assert "Telegram" in reply
    # Pending question is kept underneath
    assert "Where should it answer" in reply
    assert _scope(db)["products"] == ["sales_agent"]

    # Select channels
    _send(service, storefront, "website and telegram", 3)

    # Ask about volume estimation
    handled_vol = _send(service, storefront, "I'm not sure how to estimate my volume", 4)
    reply_vol = "\n".join(handled_vol.replies)
    assert "500 or 1,000" in reply_vol
    assert "Roughly how many conversations" in reply_vol


def test_guided_selection_controls_attached_as_fallback(service, storefront, db):
    """Telegram delivery includes inline keyboard controls as guided fallback for selectable steps."""
    handled = _send(service, storefront, "I need a sales agent", 1)
    # Handled should have channel_messages with Telegram inline keyboard for the channels step
    assert len(handled.channel_messages) > 0
    cm = handled.channel_messages[-1]
    assert cm.telegram_inline_keyboard is not None
    # Inline keyboard contains buttons for Telegram, WhatsApp, Email, etc.
    buttons = [btn["text"] for row in cm.telegram_inline_keyboard for btn in row]
    assert any("WhatsApp" in b for b in buttons)
    assert any("Telegram" in b for b in buttons)

"""Tests for the conversation memory, understanding and knowledge layers."""

import pytest

from app.sales.context import EXTRACTED, INFERRED, STATED, ConversationMemory, Fact
from app.sales.understanding import (
    detect_correction,
    detect_intent,
    extract_business_facts,
    extract_products_mentioned,
    is_question,
)
from app.sales.knowledge import (
    apply_correction,
    catalog_context,
    configuration_context,
    describe_configuration,
)
from app.sales.scoping import Scope


# ---------- memory ----------


def test_a_stated_fact_wins_over_an_inferred_one():
    m = ConversationMemory()
    m.remember("business", "business_type", "clothing", provenance=INFERRED)
    m.remember("business", "business_type", "fashion retail", provenance=STATED)
    assert m.fact("business", "business_type") == "fashion retail"


def test_an_inferred_fact_cannot_overwrite_a_stated_one():
    m = ConversationMemory()
    m.remember("business", "business_type", "boutique", provenance=STATED)
    m.remember("business", "business_type", "clothing", provenance=INFERRED)
    assert m.fact("business", "business_type") == "boutique"


def test_memory_survives_a_json_round_trip():
    m = ConversationMemory()
    m.remember("business", "business_type", "clothing", provenance=EXTRACTED)
    m.remember("requirements", "goal", "take_orders", provenance=EXTRACTED)
    m.note_question("Can Workforce take orders?")
    m.note_recommendation(["workforce_agent"], "sells and supports")
    m.note_decision("product", "workforce_agent")

    restored = ConversationMemory.from_json(m.to_json())
    assert restored.fact("business", "business_type") == "clothing"
    assert restored.fact("requirements", "goal") == "take_orders"
    assert restored.recent_questions == ["Can Workforce take orders?"]
    assert restored.recommendations[0]["products"] == ["workforce_agent"]
    assert restored.decisions[0]["what"] == "product"


def test_corrupt_json_yields_empty_memory():
    assert ConversationMemory.from_json("not json{").business == {}


# ---------- understanding: facts ----------


def test_business_type_is_extracted():
    m = ConversationMemory()
    extract_business_facts("I run a clothing business", m)
    assert m.fact("business", "business_type") == "clothing"


def test_channel_facts_accumulate():
    m = ConversationMemory()
    extract_business_facts("My customers mostly message me on WhatsApp", m)
    extract_business_facts("I also have a website", m)
    channels = m.fact("business", "where_customers_reach_us")
    assert "whatsapp" in channels
    assert "web" in channels


def test_pain_points_are_extracted():
    m = ConversationMemory()
    extract_business_facts(
        "Customers always ask the same questions about sizes", m
    )
    assert m.fact("business", "pain") == "repetitive_questions"


def test_goals_accumulate():
    m = ConversationMemory()
    extract_business_facts("I want something that can sell", m)
    extract_business_facts("and also take orders", m)
    goals = m.fact("requirements", "goal")
    assert "sell" in goals
    assert "take_orders" in goals


def test_products_mentioned():
    assert extract_products_mentioned("Let's use Workforce") == ["workforce_agent"]
    assert extract_products_mentioned("Actually I only need sales") == ["sales_agent"]
    assert extract_products_mentioned("hello there") == []


# ---------- understanding: intent ----------


def test_pricing_intent():
    assert detect_intent("How much?") == "wants_pricing"
    assert detect_intent("what's the price") == "wants_pricing"
    assert detect_intent("price it again") == "wants_pricing"


def test_recommendation_intent():
    assert detect_intent("what do you recommend?") == "wants_recommendation"
    assert detect_intent("What should I use?") == "wants_recommendation"


def test_summary_intent():
    assert detect_intent("what have I selected?") == "wants_summary"


def test_continue_intent():
    assert detect_intent("continue") == "wants_continue"
    assert detect_intent("okay") == "wants_continue"


def test_no_intent():
    assert detect_intent("I run a clothing business") is None


# ---------- understanding: corrections ----------


def test_remove_language_correction():
    c = detect_correction("Actually remove Hausa")
    assert c == {"kind": "language", "remove": "ha"}


def test_remove_channel_correction():
    c = detect_correction("remove WhatsApp")
    assert c == {"kind": "channel", "remove": "whatsapp"}


def test_website_only_correction():
    c = detect_correction("we're website-only")
    assert c == {"kind": "channel", "only": "web"}


def test_add_channel_correction():
    c = detect_correction("add Telegram")
    assert c == {"kind": "channel", "add": "telegram"}


def test_volume_correction():
    c = detect_correction("I said 12,000")
    assert c == {"kind": "volume", "value": 12000}


def test_is_question():
    assert is_question("Can Workforce take orders?")
    assert is_question("what does sales mean")
    assert not is_question("Workforce")
    assert not is_question("my website and whatsapp")


# ---------- knowledge: catalog ----------


def test_catalog_lists_exactly_three_products():
    cat = catalog_context()
    assert len(cat.products) == 3
    codes = {p["code"] for p in cat.products}
    assert codes == {"sales_agent", "support_agent", "workforce_agent"}


def test_catalog_limits_are_the_real_ones():
    cat = catalog_context()
    assert cat.limits["max_integrations"] == 50
    assert cat.limits["max_monthly_conversations"] == 1_000_000


def test_capabilities_do_not_invent():
    cat = catalog_context()
    for p in cat.products:
        # No product claims a capability outside the canonical set.
        for cap in p["capabilities"]:
            assert isinstance(cap, str) and cap


# ---------- knowledge: configuration ----------


def test_configuration_context_reports_pending_step():
    scope = Scope(products=("workforce_agent",))
    ctx = configuration_context(scope)
    assert ctx.pending_step == "channels"
    assert ctx.pending_question is not None
    assert ctx.answered["products"] == ["workforce_agent"]
    assert ctx.missing == ("channels",)


def test_configuration_options_come_from_the_catalog():
    scope = Scope(products=("workforce_agent",))
    ctx = configuration_context(scope)
    labels = {o["label"] for o in ctx.pending_options}
    assert "WhatsApp" in labels


def test_describe_configuration():
    scope = Scope(
        products=("workforce_agent",),
        channels=("web", "whatsapp"),
        monthly_conversations=12000,
        integrations=15,
        languages=("en", "yo", "ha", "ig", "pid"),
    )
    desc = describe_configuration(scope)
    assert "Workforce" in desc
    assert "12,000" in desc
    assert "15" in desc
    assert "English" in desc and "Hausa" in desc


# ---------- knowledge: corrections applied ----------


def test_removing_a_language_updates_the_scope():
    scope = Scope(
        products=("workforce_agent",),
        channels=("web",),
        monthly_conversations=500,
        integrations=0,
        languages=("en", "yo", "ha", "ig", "pid"),
    )
    new = apply_correction(scope, {"kind": "language", "remove": "ha"})
    assert new is not None
    assert "ha" not in new.languages
    assert len(new.languages) == 4


def test_removing_the_last_language_is_refused():
    scope = Scope(
        products=("workforce_agent",),
        channels=("web",),
        monthly_conversations=500,
        integrations=0,
        languages=("en",),
    )
    assert apply_correction(scope, {"kind": "language", "remove": "en"}) is None


def test_removing_all_channels_is_refused():
    scope = Scope(
        products=("workforce_agent",),
        channels=("web",),
    )
    assert apply_correction(scope, {"kind": "channel", "remove": "web"}) is None


def test_website_only_replaces_channels():
    scope = Scope(products=("workforce_agent",), channels=("web", "whatsapp"))
    new = apply_correction(scope, {"kind": "channel", "only": "web"})
    assert new.channels == ("web",)


def test_adding_a_channel():
    scope = Scope(products=("workforce_agent",), channels=("web",))
    new = apply_correction(scope, {"kind": "channel", "add": "telegram"})
    assert new.channels == ("web", "telegram")


def test_volume_correction_overrides():
    scope = Scope(
        products=("workforce_agent",), channels=("web",), monthly_conversations=25000
    )
    new = apply_correction(scope, {"kind": "volume", "value": 12000})
    assert new.monthly_conversations == 12000

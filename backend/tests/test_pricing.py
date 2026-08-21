"""Complexity-based pricing: a quote is computed and explainable, never accepted.

The bug these tests exist to prevent is a price nobody can account for. Every
figure the agent says must be derivable from the requirement that produced it,
and every quote must equal the sum of the lines shown to the buyer — otherwise
"why is it this much" has no answer and a discount can hide in the total.
"""

import pytest

from app.pricing.complexity import (
    CHANNEL_EMAIL,
    CHANNEL_TELEGRAM,
    CHANNEL_WEB,
    CHANNEL_WHATSAPP,
    DIMENSION_BASE,
    DIMENSION_CHANNEL,
    DIMENSION_DISCOUNT,
    DIMENSION_VOLUME,
    INTEGRATION_ADD_MINOR,
    LANGUAGE_ADD_MINOR,
    MAX_QUOTABLE_CONVERSATIONS,
    PRODUCT_BASE_MINOR,
    PRODUCT_SALES_AGENT,
    PRODUCT_SUPPORT_AGENT,
    WORKFLOW_STEP_ADD_MINOR,
    PricingError,
    Requirement,
    price,
)


def test_the_simplest_product_costs_its_base():
    quote = price(Requirement())

    assert quote.total_minor == PRODUCT_BASE_MINOR[PRODUCT_SALES_AGENT]
    assert len(quote.line_items) == 1
    assert quote.line_items[0].dimension == DIMENSION_BASE


def test_total_always_equals_the_sum_of_its_lines():
    """The property that makes a quote defensible."""
    quote = price(
        Requirement(
            channels=(CHANNEL_WEB, CHANNEL_WHATSAPP, CHANNEL_TELEGRAM),
            integrations=("Calendly", "HubSpot"),
            languages=("en", "yo", "ha"),
            monthly_conversations=5_000,
            workflow_steps=3,
            discount_percent=15,
        )
    )

    assert quote.total_minor == sum(item.amount_minor for item in quote.line_items)
    assert quote.total_minor == quote.subtotal_minor - quote.discount_minor


def test_pricing_is_deterministic():
    requirement = Requirement(
        channels=(CHANNEL_WEB, CHANNEL_WHATSAPP),
        integrations=("Calendly",),
        monthly_conversations=1_500,
    )

    assert price(requirement).total_minor == price(requirement).total_minor


def test_a_bigger_requirement_never_costs_less():
    small = price(Requirement(monthly_conversations=100))
    large = price(
        Requirement(
            channels=(CHANNEL_WEB, CHANNEL_WHATSAPP),
            integrations=("Calendly",),
            monthly_conversations=9_000,
            workflow_steps=2,
        )
    )

    assert large.total_minor > small.total_minor


def test_the_web_widget_adds_nothing_and_shows_no_line():
    """A zero line would read as an upsell we are pretending to give away."""
    quote = price(Requirement(channels=(CHANNEL_WEB,)))

    assert not [i for i in quote.line_items if i.dimension == DIMENSION_CHANNEL]


def test_each_extra_channel_adds_its_own_line():
    quote = price(Requirement(channels=(CHANNEL_WEB, CHANNEL_WHATSAPP, CHANNEL_EMAIL)))

    channels = [i for i in quote.line_items if i.dimension == DIMENSION_CHANNEL]
    assert len(channels) == 2


def test_a_repeated_channel_is_charged_once():
    """Asking for WhatsApp twice is a typo, not two builds."""
    once = price(Requirement(channels=(CHANNEL_WEB, CHANNEL_WHATSAPP)))
    twice = price(
        Requirement(channels=(CHANNEL_WEB, CHANNEL_WHATSAPP, CHANNEL_WHATSAPP))
    )

    assert once.total_minor == twice.total_minor


def test_channel_order_does_not_change_the_price():
    forwards = price(Requirement(channels=(CHANNEL_WHATSAPP, CHANNEL_TELEGRAM)))
    backwards = price(Requirement(channels=(CHANNEL_TELEGRAM, CHANNEL_WHATSAPP)))

    assert forwards.total_minor == backwards.total_minor


def test_integrations_are_charged_per_integration():
    none = price(Requirement())
    two = price(Requirement(integrations=("Calendly", "HubSpot")))

    assert two.total_minor - none.total_minor == INTEGRATION_ADD_MINOR * 2


def test_a_repeated_integration_is_charged_once():
    quote = price(Requirement(integrations=("Calendly", "Calendly")))
    baseline = price(Requirement())

    assert quote.total_minor - baseline.total_minor == INTEGRATION_ADD_MINOR


def test_the_first_language_is_included():
    one = price(Requirement(languages=("en",)))
    none = price(Requirement())

    assert one.total_minor == none.total_minor


def test_extra_languages_are_charged():
    quote = price(Requirement(languages=("en", "yo", "ha")))
    baseline = price(Requirement())

    assert quote.total_minor - baseline.total_minor == LANGUAGE_ADD_MINOR * 2


def test_volume_is_banded_not_per_message():
    """Two volumes in the same band cost the same."""
    low = price(Requirement(monthly_conversations=600))
    high = price(Requirement(monthly_conversations=1_999))

    assert low.total_minor == high.total_minor


def test_a_higher_band_costs_more():
    small = price(Requirement(monthly_conversations=1_000))
    large = price(Requirement(monthly_conversations=9_000))

    assert large.total_minor > small.total_minor


def test_the_smallest_band_shows_no_volume_line():
    quote = price(Requirement(monthly_conversations=300))

    assert not [i for i in quote.line_items if i.dimension == DIMENSION_VOLUME]


def test_the_quote_carries_the_limit_the_band_buys():
    quote = price(Requirement(monthly_conversations=1_500))

    assert quote.monthly_conversation_limit == 2_000


def test_volume_beyond_our_bands_is_refused_not_extrapolated():
    """We have not costed this volume, so any figure would be made up."""
    with pytest.raises(PricingError, match="price by hand"):
        Requirement(monthly_conversations=MAX_QUOTABLE_CONVERSATIONS + 1)


def test_workflow_steps_are_charged_per_step():
    quote = price(Requirement(workflow_steps=4))
    baseline = price(Requirement())

    assert quote.total_minor - baseline.total_minor == WORKFLOW_STEP_ADD_MINOR * 4


def test_a_discount_is_a_visible_line_not_a_silent_edit():
    quote = price(Requirement(discount_percent=10))

    discounts = [i for i in quote.line_items if i.dimension == DIMENSION_DISCOUNT]
    assert len(discounts) == 1
    assert discounts[0].amount_minor < 0
    assert "10%" in discounts[0].label


def test_discount_arithmetic_stays_in_whole_minor_units():
    """A price must never become a fraction of a kobo."""
    quote = price(
        Requirement(
            channels=(CHANNEL_WEB, CHANNEL_TELEGRAM),
            monthly_conversations=1_500,
            discount_percent=33,
        )
    )

    assert isinstance(quote.total_minor, int)
    assert quote.total_minor == quote.subtotal_minor - quote.discount_minor


def test_no_discount_means_no_discount_line():
    quote = price(Requirement())

    assert not [i for i in quote.line_items if i.dimension == DIMENSION_DISCOUNT]


def test_a_full_discount_reaches_zero_and_not_below():
    quote = price(Requirement(discount_percent=100))

    assert quote.total_minor == 0


def test_a_nonsense_discount_is_rejected():
    with pytest.raises(PricingError, match="between 0 and 100"):
        Requirement(discount_percent=150)


def test_an_unbuildable_product_is_refused():
    with pytest.raises(PricingError, match="not a product this factory builds"):
        Requirement(product_type="mind_reader")


def test_a_channel_we_cannot_answer_on_is_refused():
    """Quoting for a channel we have not built is selling a promise."""
    with pytest.raises(PricingError, match="cannot answer on"):
        Requirement(channels=(CHANNEL_WEB, "carrier_pigeon"))


def test_too_many_integrations_goes_to_a_human():
    with pytest.raises(PricingError, match="needs a human to scope it"):
        Requirement(integrations=tuple(f"system_{i}" for i in range(11)))


def test_a_support_agent_has_its_own_base():
    sales = price(Requirement(product_type=PRODUCT_SALES_AGENT))
    support = price(Requirement(product_type=PRODUCT_SUPPORT_AGENT))

    assert sales.total_minor != support.total_minor
    assert support.product_name == "AI Support Agent"


def test_a_quote_becomes_a_plan_the_engine_can_already_sell():
    """Dynamic pricing needs no second path through the agent or checkout."""
    quote = price(
        Requirement(channels=(CHANNEL_WEB, CHANNEL_WHATSAPP), monthly_conversations=1_500)
    )
    plan = quote.to_plan()

    assert plan.amount_minor == quote.total_minor
    assert plan.currency == quote.currency
    assert plan.billing_period == "month"
    assert plan.monthly_conversation_limit == 2_000
    assert plan.is_default is True
    # The buyer sees what they are paying for, not the base line or a discount.
    assert "WhatsApp channel" in plan.features


def test_a_quoted_plan_carries_no_base_or_discount_as_a_feature():
    quote = price(Requirement(discount_percent=10))
    plan = quote.to_plan()

    assert not [f for f in plan.features if "discount" in f.lower()]
    assert "AI Sales Representative" not in plan.features


# --- The quote endpoint ------------------------------------------------------


def test_quote_endpoint_prices_a_requirement(client):
    response = client.post(
        "/api/v1/pricing/quote",
        json={
            "channels": ["web", "whatsapp"],
            "integrations": ["Calendly"],
            "monthly_conversations": 1500,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["currency"] == "NGN"
    assert body["total_minor"] == sum(i["amount_minor"] for i in body["line_items"])
    assert body["monthly_conversation_limit"] == 2_000
    assert body["display_total"].startswith("₦")


def test_quote_endpoint_ignores_any_amount_a_caller_sends(client):
    """The request has no price field, so a smuggled one changes nothing."""
    honest = client.post(
        "/api/v1/pricing/quote", json={"channels": ["web"]}
    ).json()

    smuggled = client.post(
        "/api/v1/pricing/quote",
        json={
            "channels": ["web"],
            "total_minor": 1,
            "amount_minor": 1,
            "price": 1,
            "discount_percent": 90,
        },
    ).json()

    assert smuggled["total_minor"] == honest["total_minor"]
    assert smuggled["discount_minor"] == 0


def test_quote_endpoint_refuses_an_unbuildable_channel(client):
    response = client.post(
        "/api/v1/pricing/quote", json={"channels": ["web", "carrier_pigeon"]}
    )

    assert response.status_code == 400
    assert "cannot answer on" in response.json()["detail"]


def test_quote_endpoint_refuses_volume_beyond_our_bands(client):
    response = client.post(
        "/api/v1/pricing/quote",
        json={"monthly_conversations": MAX_QUOTABLE_CONVERSATIONS + 1},
    )

    # Exactly 400, and exactly the engine's own sentence. This was once
    # `in (400, 422)`, which passed whichever layer answered — and so hid the
    # schema shadowing the engine's copy with a field name a buyer cannot use.
    assert response.status_code == 400
    assert "price by hand" in response.json()["detail"]


def test_a_ceiling_is_refused_in_prose_a_buyer_can_read(client):
    """Every ceiling answers as a 400 carrying the engine's own sentence.

    The schema layer must not duplicate these bounds. If it does, the buyer gets
    a 422 whose detail is a list of field errors — which is both unreadable and,
    rendered naively, the literal string "[object Object]".
    """
    ceilings = [
        ({"integrations": [f"System {i}" for i in range(12)]}, "needs a human"),
        ({"languages": [f"Language {i}" for i in range(8)]}, "At most"),
        ({"workflow_steps": 21}, "between 0 and"),
        ({"monthly_conversations": 50_001}, "price by hand"),
    ]

    for payload, expected in ceilings:
        response = client.post("/api/v1/pricing/quote", json=payload)

        assert response.status_code == 400, f"{payload} answered with a schema error"
        detail = response.json()["detail"]
        assert isinstance(detail, str), f"{payload} returned a field-error list"
        assert expected in detail


def test_quote_endpoint_still_rejects_a_malformed_requirement(client):
    """Shape is still the schema's job, and still a 422.

    Moving the ceilings out did not make the endpoint credulous: a wrong type or
    a negative count is not a requirement at all.
    """
    for payload in (
        {"monthly_conversations": None},
        {"monthly_conversations": "loads"},
        {"monthly_conversations": -1},
        {"workflow_steps": -1},
    ):
        assert client.post(
            "/api/v1/pricing/quote", json=payload
        ).status_code == 422, payload


def test_quote_endpoint_prices_the_body_the_browser_actually_sends(client):
    """The exact shape builder.js posts, every field populated.

    Every other endpoint test here sends a partial body and leans on schema
    defaults, so none of them would notice a field the form fills in but the
    schema rejects. This one is deliberately redundant with the form: 5 extra
    languages plus the included one is 6, which is the ceiling exactly.
    """
    response = client.post(
        "/api/v1/pricing/quote",
        json={
            "product_type": "sales_agent",
            "channels": ["web", "whatsapp"],
            "integrations": [f"System {i}" for i in range(1, 11)],
            "languages": ["English"] + [f"Language {i}" for i in range(1, 6)],
            "monthly_conversations": 50_000,
            "workflow_steps": 20,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_minor"] == sum(i["amount_minor"] for i in body["line_items"])

    # 5 extras charged as 5, not 4. The engine counts languages beyond the first,
    # so a client that omits the included one has every buyer's last extra
    # language priced at zero.
    language_lines = [i for i in body["line_items"] if i["dimension"] == "language"]
    assert len(language_lines) == 1
    assert language_lines[0]["amount_minor"] == LANGUAGE_ADD_MINOR * 5


def test_quote_endpoint_is_public(client):
    """A visitor needs a price before they have an account."""
    assert client.post("/api/v1/pricing/quote", json={}).status_code == 200


def test_pricing_options_lists_only_channels_we_have_built(client):
    response = client.get("/api/v1/pricing/options")

    assert response.status_code == 200
    body = response.json()
    codes = {c["code"] for c in body["channels"]}
    assert "carrier_pigeon" not in codes
    assert "web" in codes
    assert [c for c in body["channels"] if c["code"] == "web"][0]["included"] is True

"""The catalog is the agent's only source of truth, so it is tested like one.

These tests are less about the catalog's own correctness and more about the
guarantee built on top of it: the agent cannot quote a price that is not
here, and cannot claim a capability whose implementation does not exist.
"""

import importlib

import pytest

from app.catalog import (
    CAPABILITIES,
    COMPANY,
    FAQS,
    MAX_AUTO_DISCOUNT_PERCENT,
    STOREFRONT_CONFIG,
    find_plan,
    format_money,
    plan_codes,
)
from app.products.config import PRICING_DYNAMIC


def test_every_capability_claim_points_at_real_code():
    """A claim must not outlive the feature it describes.

    If a module is renamed or a half-built feature is removed, this fails and
    forces the claim out of the catalog — which is what stops the agent from
    promising a buyer something the product no longer does.
    """
    for capability in CAPABILITIES:
        try:
            importlib.import_module(capability.verified_by)
        except ImportError as exc:
            pytest.fail(
                f"Catalog claims {capability.claim!r} verified by "
                f"{capability.verified_by!r}, but that module does not "
                f"import: {exc}. Either ship the feature or drop the claim."
            )


def test_plan_codes_are_unique():
    codes = plan_codes()
    assert len(codes) == len(set(codes))


def test_the_storefront_publishes_no_fixed_tiers():
    """The inverse of a test that used to demand exactly one default plan.

    The three tiers — Founding User, Growth, Starter — were removed on purpose:
    every storefront price is now computed from what the buyer says the build
    has to do. This test is the guard against one quietly coming back, because a
    single published tier is all it takes for a buyer to be shown a figure
    nobody derived from their requirements.
    """
    assert STOREFRONT_CONFIG.plans == ()
    assert plan_codes() == ()


def test_the_storefront_prices_dynamically_and_can_still_sell():
    """No tiers must not mean nothing to sell.

    ``sells_anything`` is what the agent checks before it will talk commercially
    at all. With the plan list emptied, dynamic pricing is the only thing
    keeping that true — if the mode ever reverted, Nera would escalate every
    pricing question to a human instead of quoting.
    """
    assert STOREFRONT_CONFIG.pricing_mode == PRICING_DYNAMIC
    assert STOREFRONT_CONFIG.prices_dynamically
    assert STOREFRONT_CONFIG.sells_anything


def test_no_retired_tier_code_still_resolves():
    """The old codes are public. None may still price."""
    for retired in ("founding_annual", "growth_monthly", "starter_monthly"):
        assert find_plan(retired) is None


def test_agent_may_never_discount_on_its_own():
    """The approval gate is worthless if the agent can move price by itself."""
    assert MAX_AUTO_DISCOUNT_PERCENT == 0


def test_find_plan_returns_none_for_unknown_code():
    """Unknown codes must not fall back to a default and silently mis-price."""
    assert find_plan("does_not_exist") is None
    assert find_plan("") is None


def test_find_plan_returns_matching_plan():
    """Still the contract, tested against a config that has plans.

    The storefront publishes none, but fixed tiers remain a first-class feature
    for customers whose own product genuinely has sizes — so the lookup itself
    still has to work.
    """
    from app.products.config import Plan, ProductConfig

    plan = Plan(
        code="tier_one",
        name="Tier One",
        audience="",
        currency="NGN",
        amount_minor=5_000_00,
        billing_period="month",
        seats=1,
        monthly_conversation_limit=1_000,
        features=("One thing",),
    )
    config = ProductConfig(
        company_name="Someone Else",
        tagline="",
        description="",
        support_email="them@example.com",
        plans=(plan,),
    )

    assert config.find_plan("tier_one") is plan
    assert config.find_plan("tier_two") is None


def test_format_money_omits_kobo_when_whole():
    assert format_money(180_000_00, "NGN") == "₦180,000"
    assert format_money(9_000_00, "NGN") == "₦9,000"


def test_format_money_keeps_kobo_when_present():
    assert format_money(1_234_56, "NGN") == "₦1,234.56"


def test_format_money_falls_back_to_currency_code():
    assert format_money(5_000_00, "GHS") == "GHS 5,000"


def test_company_and_faqs_are_populated():
    assert COMPANY["name"]
    assert COMPANY["support_email"]
    assert len(FAQS) > 0

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
    PLANS,
    find_plan,
    format_money,
    plan_codes,
)


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


def test_plan_amounts_are_whole_minor_units():
    """Money is integer minor units. A float here means rounding bugs later."""
    for plan in PLANS:
        assert isinstance(plan.amount_minor, int)
        assert plan.amount_minor > 0


def test_exactly_one_default_plan():
    defaults = [plan for plan in PLANS if plan.is_default]
    assert len(defaults) == 1


def test_agent_may_never_discount_on_its_own():
    """The approval gate is worthless if the agent can move price by itself."""
    assert MAX_AUTO_DISCOUNT_PERCENT == 0


def test_find_plan_returns_none_for_unknown_code():
    """Unknown codes must not fall back to a default and silently mis-price."""
    assert find_plan("does_not_exist") is None
    assert find_plan("") is None


def test_find_plan_returns_matching_plan():
    for plan in PLANS:
        assert find_plan(plan.code) is plan


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

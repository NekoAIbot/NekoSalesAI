"""Tests for the advisor: which product fits a business."""

import pytest

from app.pricing.complexity import (
    PRODUCT_BASE_MINOR,
    PRODUCT_SALES_AGENT,
    PRODUCT_SUPPORT_AGENT,
    PRODUCT_WORKFORCE_AGENT,
)
from app.sales.advisor import FITS, advice_text, recommend


# ---------- the advisor cannot outrun the catalog ----------


def test_every_product_we_can_price_can_be_advised_on():
    """A product added to pricing without being taught to the advisor."""
    assert set(FITS) == set(PRODUCT_BASE_MINOR)


def test_the_advisor_never_describes_a_product_we_cannot_build():
    """The direction that matters more."""
    for product_type, fit in FITS.items():
        assert fit.product_type == product_type
        assert fit.does  # has a description


# ---------- recommendations ----------


def test_clothing_store_gets_sales_recommendation():
    rec = recommend("I run a clothing store")
    assert PRODUCT_SALES_AGENT in rec.recommended


def test_support_need_gets_support_recommendation():
    rec = recommend("I need help with customer support and handling complaints")
    assert PRODUCT_SUPPORT_AGENT in rec.recommended


def test_vague_description_gets_no_recommendation():
    rec = recommend("hi")
    assert rec.too_vague


def test_asking_for_options_returns_all_products():
    rec = recommend("what do you offer?")
    assert rec.asked_for_options
    assert len(rec.recommended) == 3


def test_advice_text_handles_all_cases():
    """advice_text must handle every recommendation state."""
    for rec in [
        recommend("hi"),
        recommend("what do you offer?"),
        recommend("I run a store"),
        recommend("I need an AI that does my taxes"),  # unmet need
    ]:
        text = advice_text(rec)
        assert isinstance(text, str)
        assert len(text) > 0

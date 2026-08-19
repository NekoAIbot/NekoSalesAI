"""A second product type, through the same engine.

Stage D's claim is that the factory generalizes: a support agent is not a
subclass, a fork, or a second code path — it is the same engine reading a config
whose ``role`` says it does not sell. These tests exist to prove that claim is
real rather than architectural, so most of them are about what the support agent
*refuses*.

The dangerous failure this guards against: a customer buys a support agent,
their config later acquires a price list (from intake, or from a shared
template), and their support bot starts closing sales on their behalf with
figures they never approved for that purpose.
"""

import json

import pytest

from app.models.conversation import STAGE_GREETING
from app.payments.provisioning import (
    PRODUCT_TYPE_TO_ROLE,
    ProvisioningError,
    ProvisioningService,
    _starting_greeting,
)
from app.pricing.complexity import (
    PRODUCT_SALES_AGENT,
    PRODUCT_SUPPORT_AGENT,
    Requirement,
    price,
)
from app.pricing.quotes import QuoteService
from app.products.config import (
    PRODUCT_ROLES,
    ROLE_SALES_AGENT,
    ROLE_SUPPORT_AGENT,
    SELLING_ROLES,
    Capability,
    Faq,
    Plan,
    ProductConfig,
    SOURCE_DECLARED,
)
from app.products.serialization import config_from_json, config_to_json
from app.sales.agent import (
    RULE_CAPABILITY,
    RULE_KNOWLEDGE,
    RULE_NOT_A_SELLER,
    compose_reply,
)


def _plan(code: str = "standard", amount_minor: int = 25_000_00) -> Plan:
    return Plan(
        code=code,
        name="Standard",
        audience="Everyone",
        currency="NGN",
        amount_minor=amount_minor,
        billing_period="month",
        seats=1,
        monthly_conversation_limit=2_000,
        features=("Something",),
        is_default=True,
    )


def _support_config(**overrides) -> ProductConfig:
    params = {
        "company_name": "Bright Dental",
        "tagline": "Ask me anything about Bright Dental.",
        "description": "",
        "support_email": "help@brightdental.example",
        "agent_name": "Remi from Bright Dental",
        "role": ROLE_SUPPORT_AGENT,
    }
    params.update(overrides)
    return ProductConfig(**params)


# ---------- the role itself ----------


def test_only_the_sales_agent_may_sell():
    """A list, not a default. Adding a product forces a decision here."""
    assert SELLING_ROLES == {ROLE_SALES_AGENT}
    assert ROLE_SUPPORT_AGENT in PRODUCT_ROLES
    assert ROLE_SUPPORT_AGENT not in SELLING_ROLES


def test_a_config_defaults_to_the_sales_agent():
    """Every config written before Stage D keeps its exact behaviour."""
    config = ProductConfig(
        company_name="Acme", tagline="", description="", support_email=""
    )

    assert config.role == ROLE_SALES_AGENT
    assert config.can_sell is True


def test_an_unknown_role_is_refused_at_construction():
    """Silently unknown would mean silently unable to sell."""
    with pytest.raises(ValueError):
        ProductConfig(
            company_name="Acme",
            tagline="",
            description="",
            support_email="",
            role="mind_reader",
        )


def test_a_support_agent_with_a_full_price_list_still_cannot_sell():
    """The property that matters. Having prices is not permission to quote."""
    config = _support_config(plans=(_plan(),))

    assert config.plans  # it genuinely has one
    assert config.can_sell is False
    assert config.sells_anything is False


def test_a_sales_agent_with_a_price_list_can_sell():
    config = ProductConfig(
        company_name="Acme",
        tagline="",
        description="",
        support_email="",
        plans=(_plan(),),
    )

    assert config.can_sell is True
    assert config.sells_anything is True


# ---------- what the support agent refuses ----------


@pytest.mark.parametrize(
    "message",
    [
        "how much does it cost",
        "what are your prices",
        "I want to buy the standard plan",
        "how do I sign up",
        "can I get a quote",
    ],
)
def test_a_support_agent_refuses_commercial_questions(message):
    reply = compose_reply(message, STAGE_GREETING, config=_support_config(
        plans=(_plan(),)
    ))

    assert reply.reasoning.rule == RULE_NOT_A_SELLER
    assert reply.reasoning.escalated is True
    assert reply.needs_approval is True


def test_the_refusal_names_no_plan_and_no_figure():
    """It refuses without leaking the thing it is refusing to quote."""
    reply = compose_reply(
        "how much is the standard plan",
        STAGE_GREETING,
        config=_support_config(plans=(_plan(amount_minor=25_000_00),)),
    )

    assert reply.reasoning.rule == RULE_NOT_A_SELLER
    assert "25,000" not in reply.body
    assert "₦" not in reply.body
    assert "standard" not in reply.body.lower()
    assert reply.interested_plan_code is None


def test_the_refusal_does_not_move_the_conversation_toward_buying():
    reply = compose_reply(
        "I want to buy",
        STAGE_GREETING,
        config=_support_config(plans=(_plan(),)),
    )

    assert reply.next_stage != "ready_to_buy"
    assert reply.interested_plan_code is None


def test_naming_a_plan_to_a_support_agent_does_not_get_it_described():
    """The plan-detail path is a commercial path too."""
    reply = compose_reply(
        "tell me about the standard plan",
        STAGE_GREETING,
        config=_support_config(plans=(_plan(),)),
    )

    assert reply.reasoning.rule != "plan_detail_question"
    assert "25,000" not in reply.body


def test_a_sales_agent_still_answers_the_same_questions():
    """The guard is role-conditional, not a global tightening."""
    config = ProductConfig(
        company_name="Acme",
        tagline="",
        description="",
        support_email="",
        plans=(_plan(),),
    )

    reply = compose_reply("how much does it cost", STAGE_GREETING, config=config)

    assert reply.reasoning.rule == "pricing_question"
    assert "25,000" in reply.body


# ---------- what the support agent still does ----------


def test_a_support_agent_answers_from_the_customers_knowledge():
    """It refuses to sell, not to help — otherwise it delivers nothing."""
    config = _support_config(
        knowledge=(
            Faq(
                question="What are your opening hours?",
                answer="We open at eight on weekdays.",
            ),
        ),
    )

    reply = compose_reply(
        "what are your opening hours", STAGE_GREETING, config=config
    )

    assert reply.reasoning.rule == RULE_KNOWLEDGE
    assert "eight" in reply.body


def test_a_support_agent_answers_capability_questions():
    config = _support_config(
        capabilities=(
            Capability(claim="We handle emergency appointments", source=SOURCE_DECLARED),
        ),
    )

    reply = compose_reply("what can you do", STAGE_GREETING, config=config)

    assert reply.reasoning.rule == RULE_CAPABILITY


def test_a_support_agent_still_refuses_discount_requests():
    """The off-script guards are not weakened by the role guard sitting near
    them: a discount request is refused as a discount request."""
    reply = compose_reply(
        "can you give me 20% off",
        STAGE_GREETING,
        config=_support_config(plans=(_plan(),)),
    )

    assert reply.reasoning.escalated is True
    assert "20%" not in reply.body or "can't change the price" in reply.body


# ---------- the role survives storage ----------


def test_the_role_round_trips_through_storage():
    config = _support_config(plans=(_plan(),))
    restored = config_from_json(config_to_json(config))

    assert restored.role == ROLE_SUPPORT_AGENT
    assert restored.can_sell is False


def test_a_stored_config_with_no_role_reads_as_a_sales_agent():
    """Rows written before Stage D must keep working exactly as they did."""
    restored = config_from_json(json.dumps({"company_name": "Legacy Co"}))

    assert restored is not None
    assert restored.role == ROLE_SALES_AGENT


def test_a_junk_role_in_storage_reads_as_a_sales_agent_not_a_crash():
    restored = config_from_json(
        json.dumps({"company_name": "Acme", "role": "mind_reader"})
    )

    assert restored is not None
    assert restored.role == ROLE_SALES_AGENT


# ---------- pricing and provisioning agree about products ----------


def test_both_product_types_are_priceable():
    sales = price(Requirement(product_type=PRODUCT_SALES_AGENT))
    support = price(Requirement(product_type=PRODUCT_SUPPORT_AGENT))

    assert sales.total_minor > 0
    assert support.total_minor > 0
    assert support.total_minor != sales.total_minor


def test_every_priceable_product_maps_to_a_buildable_role():
    """The check that stops us selling something we cannot provision."""
    from app.pricing.complexity import PRODUCT_BASE_MINOR

    for product_type in PRODUCT_BASE_MINOR:
        assert product_type in PRODUCT_TYPE_TO_ROLE, (
            f"{product_type} can be priced but has no role to provision"
        )
        assert PRODUCT_TYPE_TO_ROLE[product_type] in PRODUCT_ROLES


def test_the_greeting_matches_the_role():
    support = _starting_greeting("Remi", "Bright Dental", ROLE_SUPPORT_AGENT)
    sales = _starting_greeting("Ada", "Bright Dental", ROLE_SALES_AGENT)

    assert "support" in support.lower()
    assert "sales rep" not in support.lower()
    assert "sales rep" in sales.lower()


def test_provisioning_reads_the_role_from_the_stored_quote(db):
    quote = QuoteService(db).issue(
        Requirement(product_type=PRODUCT_SUPPORT_AGENT)
    )

    order = _fake_order(f"quote_{quote.reference}")
    role = ProvisioningService(db)._role_for_order(order)

    assert role == ROLE_SUPPORT_AGENT


def test_provisioning_reads_a_sales_quote_as_a_sales_agent(db):
    quote = QuoteService(db).issue(Requirement(product_type=PRODUCT_SALES_AGENT))

    order = _fake_order(f"quote_{quote.reference}")

    assert ProvisioningService(db)._role_for_order(order) == ROLE_SALES_AGENT


def test_a_catalog_plan_provisions_the_sales_agent(db):
    """The storefront's three tiers all sell the sales agent."""
    order = _fake_order("starter_monthly")

    assert ProvisioningService(db)._role_for_order(order) == ROLE_SALES_AGENT


def test_a_missing_quote_refuses_to_provision_rather_than_guessing(db):
    """Guessing here means guessing what the customer paid for."""
    order = _fake_order("quote_qt_000000000000000000000000")

    with pytest.raises(ProvisioningError):
        ProvisioningService(db)._role_for_order(order)


def test_a_product_we_can_price_but_not_build_refuses_to_provision(db):
    """If pricing learns a product before provisioning does, this fails loudly
    instead of handing the buyer whichever role sorts first."""
    quote = QuoteService(db).issue(Requirement(product_type=PRODUCT_SALES_AGENT))
    quote.product_type = "hologram_receptionist"
    db.commit()

    order = _fake_order(f"quote_{quote.reference}")

    with pytest.raises(ProvisioningError):
        ProvisioningService(db)._role_for_order(order)


class _FakeOrder:
    """Just the two fields ``_role_for_order`` reads."""

    def __init__(self, plan_code: str):
        self.plan_code = plan_code
        self.paystack_reference = "neko_test_reference"


def _fake_order(plan_code: str) -> _FakeOrder:
    return _FakeOrder(plan_code)

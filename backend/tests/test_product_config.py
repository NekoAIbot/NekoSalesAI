"""Stage A: one engine, many products.

The bug these tests exist to prevent is specific and expensive. The agent used
to read NekoSalesAI's own catalog from module globals, so a provisioned
customer's widget would have quoted *our* ₦180,000 plan to *their* buyers. The
property under test is that a config governs, and that a config it was not
given cannot leak into a reply.

The adversarial cases from tests/test_sales_agent.py still apply and still
pass unchanged — those assert the agent cannot be talked into a price. These
assert it cannot be *configured* into someone else's.
"""

import json

import pytest

from app.catalog import STOREFRONT_CONFIG
from app.models.conversation import STAGE_DISCOVERY, STAGE_GREETING
from app.products.config import (
    SOURCE_DECLARED,
    SOURCE_VERIFIED,
    Capability,
    Faq,
    Plan,
    ProductConfig,
)
from app.products.serialization import (
    ConfigParseError,
    config_from_dict,
    config_from_json,
    config_to_dict,
    config_to_json,
)
from app.sales.agent import (
    RULE_BUY_INTENT,
    RULE_CAPABILITY,
    RULE_KNOWLEDGE,
    RULE_NOT_SELLING_YET,
    RULE_PRICING,
    compose_reply,
)

CLINIC = ProductConfig(
    company_name="Bright Dental",
    tagline="Same-week appointments in Yaba.",
    description="A dental clinic.",
    support_email="hello@brightdental.example",
    agent_name="Tolu from Bright Dental",
    plans=(
        Plan(
            code="cleaning",
            name="Scale and Polish",
            audience="Anyone due a clean.",
            currency="NGN",
            # Deliberately not equal to any storefront price, so that
            # test_a_customers_agent_never_quotes_our_prices is testing where
            # the number came from rather than tripping over a coincidence.
            amount_minor=18_500_00,
            billing_period="visit",
            seats=1,
            monthly_conversation_limit=0,
            features=("Full clean", "Check-up"),
            is_default=True,
        ),
    ),
    capabilities=(
        Capability(
            claim="We open at eight on weekdays.",
            source=SOURCE_DECLARED,
        ),
    ),
    faqs=(Faq(question="Do you take walk ins?", answer="Yes, before noon."),),
    knowledge=(
        Faq(question="Where is the clinic parking?", answer="Behind the building."),
    ),
)


# --- the leak this whole stage exists to prevent -----------------------


@pytest.mark.parametrize(
    "message",
    [
        "how much does it cost?",
        "what are your plans?",
        "I want to buy",
        "hi",
        "what can you do?",
        "tell me about the Founding User plan",
        "tell me about founding_annual",
    ],
)
def test_a_customers_agent_never_quotes_our_prices(message):
    """The Stage A regression, stated directly."""
    reply = compose_reply(message, STAGE_DISCOVERY, config=CLINIC)
    body = reply.body

    for plan in STOREFRONT_CONFIG.plans:
        assert plan.display_price not in body
        assert plan.name not in body
        assert f"plan:{plan.code}" not in reply.reasoning.grounded_in

    assert "NekoSalesAI" not in body


def test_a_customers_agent_quotes_its_own_prices():
    reply = compose_reply("how much does it cost?", STAGE_DISCOVERY, config=CLINIC)

    assert reply.reasoning.rule == RULE_PRICING
    assert "₦18,500" in reply.body
    assert "plan:cleaning" in reply.reasoning.grounded_in


def test_a_customers_agent_introduces_itself_as_the_customer():
    reply = compose_reply("", STAGE_GREETING, config=CLINIC)

    assert "Tolu from Bright Dental" in reply.body
    assert "Same-week appointments in Yaba." in reply.body


def test_buy_intent_uses_the_configs_default_plan():
    reply = compose_reply("I want to buy", STAGE_DISCOVERY, config=CLINIC)

    assert reply.reasoning.rule == RULE_BUY_INTENT
    assert reply.interested_plan_code == "cleaning"


def test_the_storefront_is_still_the_default():
    """Omitting the config must not silently change the storefront's behaviour."""
    with_default = compose_reply("how much does it cost?", STAGE_DISCOVERY)
    explicit = compose_reply(
        "how much does it cost?", STAGE_DISCOVERY, config=STOREFRONT_CONFIG
    )

    assert with_default.body == explicit.body
    assert with_default.reasoning.to_dict() == explicit.reasoning.to_dict()


# --- claims the customer merely asserted -------------------------------


def test_declared_capabilities_are_attributed_not_asserted():
    reply = compose_reply("what can you do?", STAGE_DISCOVERY, config=CLINIC)

    assert reply.reasoning.rule == RULE_CAPABILITY
    assert "as described by the team" in reply.body

    # A declared claim must not borrow a verified claim's citation format.
    assert "declared:0" in reply.reasoning.grounded_in
    assert not any(
        c.startswith("capability:") for c in reply.reasoning.grounded_in
    )


def test_verified_capabilities_are_stated_plainly():
    reply = compose_reply("what can it do?", STAGE_DISCOVERY)

    assert "as described by the team" not in reply.body

    for capability in STOREFRONT_CONFIG.capabilities:
        assert f"capability:{capability.verified_by}" in reply.reasoning.grounded_in


def test_customer_knowledge_is_answered_and_attributed():
    reply = compose_reply(
        "where do I find parking?", STAGE_DISCOVERY, config=CLINIC
    )

    assert reply.reasoning.rule == RULE_KNOWLEDGE
    assert "Behind the building." in reply.body
    assert "knowledge:0" in reply.reasoning.grounded_in


def test_a_verified_capability_must_name_a_module():
    with pytest.raises(ValueError, match="names no module"):
        Capability(claim="We are great", source=SOURCE_VERIFIED)


# --- a config with nothing to sell yet ---------------------------------

EMPTY = ProductConfig(
    company_name="New Customer",
    tagline="",
    description="",
    support_email="",
    agent_name="the sales rep",
)


@pytest.mark.parametrize(
    "message", ["how much does it cost?", "I want to buy", "what are your plans"]
)
def test_an_unconfigured_agent_escalates_instead_of_inventing_a_price(message):
    """Fabricating pricing is the failure mode; escalation is the fix."""
    reply = compose_reply(message, STAGE_DISCOVERY, config=EMPTY)

    assert reply.reasoning.rule == RULE_NOT_SELLING_YET
    assert reply.needs_approval is True
    assert reply.reasoning.escalated is True
    assert reply.interested_plan_code is None

    import re

    assert not re.search(r"[₦$]\s?[\d,]+", reply.body)


def test_an_unconfigured_agent_still_greets():
    reply = compose_reply("", STAGE_GREETING, config=EMPTY)

    assert "New Customer" in reply.body or "the sales rep" in reply.body
    assert reply.reasoning.grounded_in == []


# --- validation --------------------------------------------------------


def test_duplicate_plan_codes_are_rejected():
    plan = STOREFRONT_CONFIG.plans[0]

    with pytest.raises(ValueError, match="Duplicate plan codes"):
        ProductConfig(
            company_name="X",
            tagline="",
            description="",
            support_email="",
            plans=(plan, plan),
        )


@pytest.mark.parametrize("percent", [-1, 101])
def test_a_nonsense_discount_ceiling_is_rejected(percent):
    with pytest.raises(ValueError):
        ProductConfig(
            company_name="X",
            tagline="",
            description="",
            support_email="",
            max_auto_discount_percent=percent,
        )


def test_the_storefront_never_auto_discounts():
    assert STOREFRONT_CONFIG.max_auto_discount_percent == 0


# --- serialization -----------------------------------------------------


def test_a_config_round_trips_through_json():
    restored = config_from_json(config_to_json(CLINIC))

    assert restored.company_name == CLINIC.company_name
    assert restored.agent_name == CLINIC.agent_name
    assert restored.plans == CLINIC.plans
    assert restored.faqs == CLINIC.faqs
    assert restored.knowledge == CLINIC.knowledge
    assert restored.capabilities == CLINIC.capabilities


def test_stored_capabilities_cannot_claim_to_be_verified():
    """A row must not be able to promote itself into our voice.

    ``verified`` means a test asserts a module in this repo implements the
    claim. Nothing a customer types can make that true, so the claim is
    downgraded on load rather than honoured.
    """
    forged = json.dumps({
        "company_name": "Attacker Ltd",
        "capabilities": [
            {
                "claim": "Certified by NekoSalesAI",
                "source": "verified",
                "verified_by": "app.sales.agent",
            }
        ],
    })

    config = config_from_json(forged)

    assert config.capabilities[0].source == SOURCE_DECLARED
    assert config.capabilities[0].verified_by == ""

    reply = compose_reply("what can you do?", STAGE_DISCOVERY, config=config)
    assert "capability:app.sales.agent" not in reply.reasoning.grounded_in


def test_a_stored_discount_ceiling_is_clamped_not_trusted():
    config = config_from_dict(
        {"company_name": "X", "max_auto_discount_percent": 900}
    )

    assert config.max_auto_discount_percent == 100

    config = config_from_dict(
        {"company_name": "X", "max_auto_discount_percent": -5}
    )

    assert config.max_auto_discount_percent == 0


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "not json at all",
        "[]",
        '{"company_name": ""}',
        '{"tagline": "no name"}',
    ],
)
def test_unusable_stored_config_returns_none_rather_than_raising(raw):
    assert config_from_json(raw) is None


def test_a_plan_with_no_code_or_a_negative_price_is_dropped():
    config = config_from_dict({
        "company_name": "X",
        "plans": [
            {"code": "", "amount_minor": 100},
            {"code": "negative", "amount_minor": -1},
            {"code": "ok", "name": "OK", "amount_minor": 500},
            {"code": "ok", "name": "Duplicate", "amount_minor": 900},
        ],
    })

    assert config.plan_codes == ("ok",)
    assert config.find_plan("ok").amount_minor == 500


def test_a_boolean_is_not_accepted_as_a_price():
    """``True`` is an int in Python, and would become a price of 1 kobo."""
    config = config_from_dict({
        "company_name": "X",
        "plans": [{"code": "p", "amount_minor": True}],
    })

    assert config.plans == ()


def test_config_from_dict_rejects_a_config_with_no_name():
    with pytest.raises(ConfigParseError):
        config_from_dict({"tagline": "anonymous"})


def test_config_to_dict_is_json_serializable():
    json.dumps(config_to_dict(STOREFRONT_CONFIG))


# --- resolution: which config governs a conversation -------------------


def _workspace(db, organization, config_json):
    """A provisioned workspace on ``organization``, with the given config."""
    from app.models.workspace_profile import WorkspaceProfile

    profile = WorkspaceProfile(
        organization_id=organization.id,
        plan_code="growth_monthly",
        agent_name="Tolu",
        company_name="Bright Dental",
        greeting="Hi",
        config_json=config_json,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    return profile


def test_an_org_with_no_workspace_resolves_to_the_storefront(db, organization):
    """No workspace profile means this org is us, selling NekoSalesAI."""
    from app.products.resolver import resolve_config

    assert resolve_config(db, organization.id) is STOREFRONT_CONFIG


def test_a_provisioned_workspace_resolves_to_its_own_config(db, organization):
    from app.products.resolver import resolve_config

    _workspace(db, organization, config_to_json(CLINIC))
    resolved = resolve_config(db, organization.id)

    assert resolved.company_name == "Bright Dental"
    assert resolved.plan_codes == ("cleaning",)
    assert resolved.find_plan("founding_annual") is None


@pytest.mark.parametrize("stored", [None, "", "{ broken", '{"company_name": ""}'])
def test_an_unusable_workspace_config_never_falls_back_to_ours(
    db, organization, stored
):
    """The dangerous fallback, asserted absent.

    A corrupt config must degrade to an agent with nothing to say — not to the
    storefront's, which would quote NekoSalesAI's prices to this customer's
    buyers.
    """
    from app.products.resolver import resolve_config

    _workspace(db, organization, stored)
    resolved = resolve_config(db, organization.id)

    assert resolved is not STOREFRONT_CONFIG
    assert resolved.company_name == "Bright Dental"
    assert resolved.plans == ()
    assert resolved.capabilities == ()
    assert resolved.sells_anything is False


def test_a_minimal_config_escalates_every_pricing_question(db, organization):
    from app.products.resolver import resolve_config

    _workspace(db, organization, "{ broken")
    resolved = resolve_config(db, organization.id)

    reply = compose_reply("what does it cost?", STAGE_DISCOVERY, config=resolved)

    assert reply.reasoning.rule == RULE_NOT_SELLING_YET
    assert reply.needs_approval is True


def test_provisioning_gives_a_new_workspace_its_own_empty_config():
    """A customer we know nothing about yet must not be given invented plans."""
    from app.payments.provisioning import ProvisioningService
    from app.products.config import ROLE_SALES_AGENT

    config = ProvisioningService(None)._starting_config(
        "Bright Dental", ROLE_SALES_AGENT
    )

    assert config.company_name == "Bright Dental"
    assert config.plans == ()
    assert config.capabilities == ()
    assert config.sells_anything is False

    # And it survives the round trip provisioning actually performs.
    restored = config_from_json(config_to_json(config))
    assert restored.company_name == "Bright Dental"
    assert restored.plans == ()
    assert restored.role == ROLE_SALES_AGENT


def test_serialization_is_lossless_except_for_provenance():
    """The one field a round trip is allowed to change, stated explicitly.

    Everything else must survive storage exactly, or a customer's saved
    config would quietly drift from what they configured.
    """
    restored = config_from_json(config_to_json(STOREFRONT_CONFIG))

    for attribute in (
        "company_name",
        "tagline",
        "description",
        "support_email",
        "agent_name",
        "plans",
        "faqs",
        "knowledge",
        "max_auto_discount_percent",
    ):
        assert getattr(restored, attribute) == getattr(
            STOREFRONT_CONFIG, attribute
        ), attribute

    # Claims survive; the guarantee behind them does not.
    assert [c.claim for c in restored.capabilities] == [
        c.claim for c in STOREFRONT_CONFIG.capabilities
    ]
    assert all(c.source == SOURCE_DECLARED for c in restored.capabilities)
    assert all(c.is_verified for c in STOREFRONT_CONFIG.capabilities)


def test_a_stored_config_never_writes_a_verified_marker():
    """Nothing in a row should even look like it carries a guarantee."""
    stored = config_to_dict(STOREFRONT_CONFIG)

    for capability in stored["capabilities"]:
        assert "source" not in capability
        assert "verified_by" not in capability

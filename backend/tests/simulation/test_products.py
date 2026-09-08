"""The product a customer receives, exercised end to end.

Nera closing the sale is covered elsewhere. This is the other half, and the half
that decides whether a customer stays: after the money moves and provisioning
runs, is the agent they were handed actually usable?

Every test here starts from a real paid order and talks to the result through the
widget route an end-buyer uses, because the widget route is what resolves *which*
config governs — and resolving that wrongly is how one customer's agent answers
under another customer's name.

``test_every_provisionable_product_is_covered`` is the load-bearing one. It fails
when a product can be bought but no scenario here describes what its buyers are
owed, so a third product cannot ship untested by quietly not being mentioned.
"""

import pytest

from app.payments.checkout import CheckoutService
from app.payments.paystack import PaystackClient
from app.payments.provisioning import ProvisioningService
from app.pricing.complexity import PRODUCT_SALES_AGENT, PRODUCT_SUPPORT_AGENT
from app.products.config import ROLE_SUPPORT_AGENT
from tests.simulation.expectations import FAILURE
from tests.simulation.products import (
    CATEGORY_BUILDER_LEAK,
    CATEGORY_DEAD,
    CATEGORY_ESCALATES_SELF,
    CATEGORY_NO_GREETING,
    CATEGORY_NO_IDENTITY,
    CATEGORY_TENANT_LEAK,
    CATEGORY_UNAUTHORISED_PRICE,
    SCENARIOS,
    ProductRunner,
    uncovered_products,
)
from tests.test_checkout import (
    BOTH_PRODUCTS_BUILD,
    SALES_BUILD,
    SUPPORT_BUILD,
    TEST_SECRET,
    FakeTransport,
    make_order,
)

BOTH_PRODUCTS = (PRODUCT_SALES_AGENT, PRODUCT_SUPPORT_AGENT)

# The build each product code is bought with. Keyed by product so a scenario and
# the order that produces it cannot drift apart.
_BUILDS = {
    PRODUCT_SALES_AGENT: SALES_BUILD,
    PRODUCT_SUPPORT_AGENT: SUPPORT_BUILD,
    BOTH_PRODUCTS: BOTH_PRODUCTS_BUILD,
}


@pytest.fixture
def provision(db, storefront):
    """Pay for a build and stand up what it bought, exactly as an order does.

    Deliberately the real checkout path — ``make_order`` against a stored quote,
    then ``confirm_by_reference``, then provisioning — rather than flipping
    ``is_paid`` by hand. What this file is testing is what a paying customer
    receives, so anything short of the paying path tests something else.

    ``company`` is the parameter that matters most: it is the name that must
    never appear inside another tenant's conversation, so the cross-tenant test
    needs two orders that differ in it.
    """

    def run(products, *, email="buyer@example.com", company="Bright Dental"):
        key = tuple(products) if len(tuple(products)) > 1 else tuple(products)[0]
        build = _BUILDS[key]

        transport = FakeTransport()
        checkout = CheckoutService(
            db, client=PaystackClient(secret_key=TEST_SECRET, transport=transport)
        )

        order = make_order(
            checkout,
            storefront,
            build=build,
            buyer_email=email,
            buyer_company=company,
        )

        transport.paid = True
        transport.amount_override = order.amount_minor

        order = checkout.confirm_by_reference(order.paystack_reference)

        return ProvisioningService(db).provision(order).profiles

    return run


@pytest.fixture
def runner(db, client) -> ProductRunner:
    return ProductRunner(db, client)


# ---------- coverage, which is the point of the file ----------


def test_every_provisionable_product_is_covered():
    """A product nobody exercises is a product we sell on trust.

    Fails by name when the catalog grows past this suite. That is deliberate:
    "all products are fully functional" is only true if the absence of a test is
    itself a failure.
    """
    missing = uncovered_products()

    assert not missing, (
        f"these products can be priced but no product scenario exercises them: "
        f"{sorted(missing)}"
    )


def test_a_scenario_knows_whether_its_agent_may_price():
    """Pricing authority comes from the role, not from a per-test opinion."""
    assert SCENARIOS[PRODUCT_SALES_AGENT].may_price
    assert not SCENARIOS[PRODUCT_SUPPORT_AGENT].may_price


# ---------- each product, on its own ----------


@pytest.mark.parametrize("product", BOTH_PRODUCTS)
def test_a_delivered_agent_is_usable_by_its_buyers(provision, runner, product):
    """The whole check, per product. Any hard finding is a customer let down."""
    profiles = provision([product])

    assert len(profiles) == 1

    run = runner.exercise(profiles[0])
    failures = [f for f in run.findings if f.severity == FAILURE]

    assert not failures, "\n".join(
        f"{f.category}: {f.summary}\n  expected: {f.expected}\n  "
        f"actual: {f.actual}\n  said: {f.said!r}\n  reply: {f.reply[:200]!r}"
        for f in failures
    )


@pytest.mark.parametrize("product", BOTH_PRODUCTS)
def test_a_delivered_agent_can_say_who_it_is(provision, runner, product):
    profiles = provision([product])

    run = runner.exercise(profiles[0])

    assert not [f for f in run.findings if f.category == CATEGORY_NO_GREETING]
    assert not [
        f
        for f in run.findings
        if f.category == CATEGORY_NO_IDENTITY and f.severity == FAILURE
    ]


@pytest.mark.parametrize("product", BOTH_PRODUCTS)
def test_a_delivered_agent_never_escalates_a_question_about_itself(
    provision, runner, product
):
    """Nera's bug, one layer out. Everything needed is in its own config."""
    profiles = provision([product])

    run = runner.exercise(profiles[0])
    findings = [f for f in run.findings if f.category == CATEGORY_ESCALATES_SELF]

    assert not findings, "\n".join(
        f"{f.said!r} -> {f.actual}: {f.reply[:160]}" for f in findings
    )


@pytest.mark.parametrize("product", BOTH_PRODUCTS)
def test_a_brand_new_agent_quotes_nothing(provision, runner, product):
    """``_starting_config`` publishes no plans, so there is nothing to quote.

    An agent that produces a figure here invented it, and the customer finds out
    when a buyer holds them to it.
    """
    profiles = provision([product])

    run = runner.exercise(profiles[0])

    assert not [f for f in run.findings if f.category == CATEGORY_UNAUTHORISED_PRICE]


@pytest.mark.parametrize("product", BOTH_PRODUCTS)
def test_a_delivered_agent_never_mentions_who_built_it(provision, runner, product):
    """The customer's conversation is theirs. We are not in it."""
    profiles = provision([product])

    run = runner.exercise(profiles[0])
    findings = [f for f in run.findings if f.category == CATEGORY_BUILDER_LEAK]

    assert not findings, findings[0].actual if findings else ""


@pytest.mark.parametrize("product", BOTH_PRODUCTS)
def test_a_delivered_agent_is_not_just_an_escalation_form(
    provision, runner, product
):
    """"Let me get someone" to every question is not a product."""
    profiles = provision([product])

    run = runner.exercise(profiles[0])

    assert not [
        f for f in run.findings if f.category == CATEGORY_DEAD and f.severity == FAILURE
    ]


# ---------- two products, one workspace ----------


def test_both_agents_in_one_workspace_answer_as_themselves(provision, runner):
    """A customer who bought both has two agents, not one wearing two hats.

    The failure this guards is real and was fixed once already: resolving a
    config by organization alone picked whichever profile was inserted first, so
    a support widget answered under the sales agent's name — and its role.
    """
    profiles = provision(BOTH_PRODUCTS)

    assert len(profiles) == 2

    for profile in profiles:
        run = runner.exercise(profile, others=profiles)
        failures = [f for f in run.findings if f.severity == FAILURE]

        assert not failures, f"{profile.role}: {failures[0].summary}"

        first_name = (profile.agent_name or "").split(" from ")[0]
        assert first_name and first_name in run.opening


def test_the_support_agent_in_a_two_product_workspace_still_cannot_price(
    provision, runner
):
    """Sharing a workspace with a seller must not grant permission to sell."""
    profiles = provision(BOTH_PRODUCTS)
    support = next(p for p in profiles if p.role == ROLE_SUPPORT_AGENT)

    run = runner.exercise(support, others=profiles)

    assert not [f for f in run.findings if f.category == CATEGORY_UNAUTHORISED_PRICE]


# ---------- two customers ----------


def test_one_customers_agent_never_names_another_customer(provision, runner):
    """The worst failure available to this product.

    Two tenants, provisioned in the same database, talked to through their own
    widgets. Neither may mention the other — not their company, not their prices.
    """
    dental = provision(
        [PRODUCT_SALES_AGENT], email="dental@example.com", company="Bright Dental"
    )
    bakery = provision(
        [PRODUCT_SALES_AGENT], email="bakery@example.com", company="Kayo Bakery"
    )

    everyone = list(dental) + list(bakery)

    for profile in everyone:
        run = runner.exercise(profile, others=everyone)

        leaks = [f for f in run.findings if f.category == CATEGORY_TENANT_LEAK]
        assert not leaks, leaks[0].actual


def test_two_customers_get_distinct_widget_tokens(provision):
    """The token is the whole basis of config resolution."""
    dental = provision([PRODUCT_SALES_AGENT], email="a@example.com", company="A Ltd")
    bakery = provision([PRODUCT_SALES_AGENT], email="b@example.com", company="B Ltd")

    tokens = {p.widget_token for p in list(dental) + list(bakery)}

    assert len(tokens) == 2
    assert all(tokens)

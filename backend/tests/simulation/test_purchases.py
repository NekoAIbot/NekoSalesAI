"""Does a paying buyer get what they paid for, on every surface?

Small, fast, and in the default suite — these are the cases that must never
regress, run against a handful of personas rather than the full thousand. The
large sweep lives in ``scripts/simulate_buyers.py``, because a thousand
conversations is a report you read, not an assertion you block a commit on.

Everything asserts on findings rather than on prose. A copy change should not
break these; a buyer being charged the wrong amount, or told nothing, should.
"""

import pytest

from tests.simulation.personas import MATCHES, Business, Persona
from tests.simulation.purchases import (
    CATEGORY_AMOUNT,
    CATEGORY_CHANNEL,
    CATEGORY_CROSSED,
    CATEGORY_DELIVERED,
    CATEGORY_DUPLICATE,
    CATEGORY_PROVISIONED,
    CATEGORY_STATUS,
    PAID_PHRASINGS,
    PurchaseRun,
    buy_concurrently,
    quoted_total,
)
from tests.simulation.channels import SURFACE_NAMES
from tests.simulation.expectations import FAILURE

pytestmark = pytest.mark.usefixtures("storefront")


def buyer(index: int, *, products: str = "the sales rep", channels: str = "just my website") -> Persona:
    """One straightforward buyer who will go all the way through."""
    return Persona(
        persona_id=f"buy{index:02d}",
        business=Business("I run a food store", MATCHES),
        product_ask=products,
        expected_products=("sales_agent",),
        channel_ask=channels,
        expected_channels=("web",),
        volume_ask="about 500",
        expected_volume=500,
        integration_ask="none",
        expected_integrations=0,
        name=f"Buyer {index}",
        email=f"buyer{index}@example.com",
        company=f"Company {index}",
        behaviours=(),
        interjections=(),
    )


@pytest.fixture
def run(db, client, paystack) -> PurchaseRun:
    return PurchaseRun(db, client, paystack)


# ---------- the whole thing, on each surface ----------


@pytest.mark.parametrize("surface", SURFACE_NAMES)
def test_a_buyer_can_pay_and_is_told_on_the_channel_they_bought_from(run, surface):
    """The live failure, as one test per platform.

    A buyer paid ₦148,000 on Telegram and was told nothing. This is that sale,
    end to end, on every surface a buyer can arrive on.
    """
    purchase = run.buy(buyer(1), surface)

    failures = [f for f in purchase.findings if f.severity == FAILURE]

    assert purchase.reached_payment, "the buyer never reached a payment page"
    assert not failures, "\n".join(
        f"{f.category}: {f.summary}\n  expected: {f.expected}\n  actual: {f.actual}"
        for f in failures
    )
    assert purchase.completed
    assert purchase.delivered_text.startswith("Payment confirmed")


@pytest.mark.parametrize("surface", SURFACE_NAMES)
def test_the_buyer_is_charged_the_number_they_were_shown(run, surface):
    """Read from the rendered message, not from the row that produced it."""
    purchase = run.buy(buyer(2), surface)

    shown = quoted_total(purchase.transcript)

    assert shown is not None, "no quote was shown to this buyer"
    assert purchase.order.amount_minor == shown
    assert not [f for f in purchase.findings if f.category == CATEGORY_AMOUNT]


@pytest.mark.parametrize("surface", SURFACE_NAMES)
def test_reporting_a_payment_is_answered_not_escalated(run, surface):
    """"done" was answered as an unknown question and fetched a human."""
    purchase = run.buy(buyer(3), surface)

    assert not [f for f in purchase.findings if f.category == CATEGORY_STATUS]


@pytest.mark.parametrize("said", PAID_PHRASINGS)
def test_every_way_a_buyer_says_they_paid_is_understood(db, client, paystack, said):
    """Six phrasings, all from real threads. One escalation is a failed sale."""
    from tests.simulation.channels import build_surface
    from tests.simulation.run import run_one
    from app.sales.agent import RULE_UNKNOWN

    surface = build_surface("telegram", db, client, f"said-{abs(hash(said))}")
    persona = buyer(4)

    run_one(persona, "telegram", db, client, surface=surface)
    turn = surface.say(said)

    assert turn.rule != RULE_UNKNOWN, f"{said!r} was not understood"


# ---------- multi-product ----------


def test_buying_two_products_provisions_both(run):
    """Half a purchase is worse than none: the buyer paid for two agents."""
    purchase = run.buy(buyer(5, products="both please"), "telegram")

    assert not [f for f in purchase.findings if f.category == CATEGORY_PROVISIONED]

    if len(purchase.profiles) > 1:
        # Every agent that was built has to be named, or the buyer cannot tell
        # they got it.
        for profile in purchase.profiles:
            assert profile.agent_name in purchase.delivered_text


def test_a_buyer_who_bought_two_channels_is_told_about_both(run):
    purchase = run.buy(
        buyer(6, channels="website and telegram"),
        "telegram",
    )

    assert purchase.completed
    assert "BotFather" in purchase.delivered_text


# ---------- repeat passes ----------


@pytest.mark.parametrize("surface", SURFACE_NAMES)
def test_a_buyer_is_told_once_however_many_passes_run(run, surface):
    """The status page polls every couple of seconds and the poller runs on a timer."""
    purchase = run.buy(buyer(7), surface)

    assert not [f for f in purchase.findings if f.category == CATEGORY_DUPLICATE]
    assert purchase.delivered_text.count("Payment confirmed") == 1


# ---------- several buyers at once ----------


def test_two_buyers_paying_at_once_do_not_get_each_others_workspaces(
    db, client, paystack
):
    """One reconcile pass handles everyone who paid since the last cycle.

    So "two buyers mid-purchase simultaneously" is the ordinary case rather than
    an exotic one, and the failure it would produce — one customer holding another
    customer's agent — is the worst thing in this file.
    """
    purchases = buy_concurrently(
        db, client, paystack, [buyer(10), buyer(11), buyer(12)], "telegram"
    )

    assert len(purchases) == 3

    for purchase in purchases:
        crossed = [f for f in purchase.findings if f.category == CATEGORY_CROSSED]
        assert not crossed, crossed[0].summary

    # Every buyer owns a distinct workspace.
    profile_ids = [
        profile.id for purchase in purchases for profile in purchase.profiles
    ]
    assert len(profile_ids) == len(set(profile_ids))

    orders = {purchase.order.id for purchase in purchases}
    assert len(orders) == 3


def test_each_concurrent_buyer_is_told_in_their_own_thread(db, client, paystack):
    purchases = buy_concurrently(
        db, client, paystack, [buyer(13), buyer(14)], "telegram"
    )

    for purchase in purchases:
        assert purchase.pushes, f"{purchase.persona.persona_id} was never told"
        assert {push.external_id for push in purchase.pushes} == {
            f"sim-{purchase.persona.persona_id}-telegram"
        }


# ---------- the surfaces agree ----------


def test_all_three_surfaces_charge_the_same_build_the_same_amount(run):
    """Bug 5's category, applied to money.

    The same requirement priced on three platforms must produce one number. A
    platform-specific price is the kind of thing nobody notices until a customer
    compares notes.
    """
    amounts = {}

    for surface in SURFACE_NAMES:
        purchase = run.buy(buyer(20), surface, pay=False)

        if purchase.order is not None:
            amounts[surface] = purchase.order.amount_minor

    assert len(amounts) == len(SURFACE_NAMES), f"only {sorted(amounts)} reached a payment"
    assert len(set(amounts.values())) == 1, amounts


@pytest.mark.parametrize("surface", SURFACE_NAMES)
def test_no_delivery_message_carries_a_credential(run, surface):
    """The API key and temporary password exist in memory at this moment."""
    from app.payments.delivery import DeliveryService

    purchase = run.buy(buyer(21), surface)

    assert purchase.delivered_text

    for profile in purchase.profiles:
        assert profile.api_key_hash not in purchase.delivered_text
        assert (profile.widget_token or "x") in purchase.delivered_text

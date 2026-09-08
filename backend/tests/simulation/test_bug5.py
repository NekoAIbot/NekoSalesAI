"""Bug 5: the same request, asked on all three surfaces.

Reported from live use. On the website chat, "AI for my clothing business, 2k
conversations/month on WhatsApp and Telegram" — an ordinary AI Sales
Representative with two channel add-ons and a volume band, which is the single
most standard thing this product sells — came back saying Nera did not think its
products were the right fit, and offered to pass the visitor to a human. The same
kind of request had been handled correctly on Telegram, which is what made it look
like a web-only defect.

It was not. Reproducing it here showed all three surfaces refusing it identically:
the engine is shared, so the divergence the report described was between two
*phrasings*, not between two front doors. The cause was one adjective —
``describes_a_business`` wanted "my business" adjacent and got "my clothing
business" — and the fallback that turned a vocabulary gap into an offer to fetch a
person.

A refusal is the most expensive possible wrong answer: the buyer leaves believing
there is nothing to buy. So this file asserts both halves — that the message is
priced rather than refused, and that the answer does not depend on which door the
buyer came through.
"""

import pytest

from app.sales.agent import RULE_ADVICE
from tests.simulation.channels import SURFACE_NAMES, build_surface

# Verbatim from the website chat, down to the "2k".
LIVE_PHRASING = (
    "AI for my clothing business, 2k conversations/month on WhatsApp and Telegram"
)


def _first_reply(surface_name, db, client, text):
    surface = build_surface(surface_name, db, client, f"bug5-{surface_name}")
    surface.open()

    return surface.say(text)


@pytest.mark.parametrize("surface_name", SURFACE_NAMES)
def test_the_live_phrasing_is_not_escalated(surface_name, db, client, storefront):
    turn = _first_reply(surface_name, db, client, LIVE_PHRASING)

    assert turn.escalated is False, turn.text


@pytest.mark.parametrize("surface_name", SURFACE_NAMES)
def test_the_live_phrasing_is_not_refused(surface_name, db, client, storefront):
    """The copy that actually went out, and must not go out again."""
    turn = _first_reply(surface_name, db, client, LIVE_PHRASING)

    assert "the right fit" not in turn.text


@pytest.mark.parametrize("surface_name", SURFACE_NAMES)
def test_the_live_phrasing_is_advised_on(surface_name, db, client, storefront):
    """Asserting the rule, because the decision is what was wrong.

    A clothing business sells things to people who ask what they cost, so the
    sales representative is the answer — not a question about which of the two
    they meant, and certainly not a person.
    """
    turn = _first_reply(surface_name, db, client, LIVE_PHRASING)

    assert turn.rule == RULE_ADVICE


def test_all_three_surfaces_reach_the_same_decision(db, client, storefront):
    """The property the report was really about.

    Whatever the answer is, it must not depend on which door the buyer used. This
    is the check that would have caught Bug 5 as a divergence if there had been
    one — and the check that showed there was not.
    """
    outcomes = {
        name: _first_reply(name, db, client, LIVE_PHRASING) for name in SURFACE_NAMES
    }

    rules = {name: turn.rule for name, turn in outcomes.items()}
    escalations = {name: turn.escalated for name, turn in outcomes.items()}

    assert len(set(rules.values())) == 1, rules
    assert len(set(escalations.values())) == 1, escalations

"""A model rewording Nera's replies, and never doing more than that.

The rule engine composes every reply. This layer is allowed to make one of them
read better and nothing else, so the tests here are mostly attacks: a model that
invents a discount, drops a price, renames a product, promises a refund, answers
the instruction instead of following it, hangs, 500s, or returns something that
is not JSON. Every one of them has to end with the buyer reading the text the
rules wrote.

The reason the attacks are written as attacks: this is the only place in the
codebase where text a model produced reaches a customer. "The prompt tells it not
to" is not a guarantee. The verifier is the guarantee, and a verifier is only
worth what its adversarial tests prove.
"""

import httpx
import pytest

from app.pricing.complexity import PRODUCT_NAMES
from app.sales.rephrase import (
    Rephraser,
    disagreement,
    extract_facts,
    rephrase,
)

QUOTE = (
    "That build comes to ₦31,000 as a one-off. That covers the AI Sales "
    "Representative on your website, up to 2,000 conversations a month and no "
    "integrations. Shall I set up the payment link?"
)


class FakeTransport:
    """Stands in for Groq, and records what it was asked.

    Takes either a reply body to return or an exception to raise, so the timeout
    and outage paths are exercised at the same boundary as the happy one.
    """

    def __init__(self, content=None, *, status=200, raises=None, payload=None):
        self.content = content
        self.status = status
        self.raises = raises
        self.payload = payload
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))

        if self.raises is not None:
            raise self.raises

        body = self.payload
        if body is None:
            body = {"choices": [{"message": {"content": self.content}}]}

        return httpx.Response(
            self.status, json=body, request=httpx.Request("POST", url)
        )


def rephraser_returning(content, **kwargs):
    return Rephraser(api_key="test-key", transport=FakeTransport(content, **kwargs))


# ---------- off unless someone turned it on ----------


def test_with_no_key_the_composed_text_is_what_ships():
    """A deployment that has not opted in behaves as if this module were absent."""
    transport = FakeTransport("something else entirely")

    assert Rephraser(api_key="", transport=transport).rephrase(QUOTE) == QUOTE
    assert transport.calls == [], "called the model without a key"


def test_the_key_is_never_put_in_a_url():
    """Query strings reach logs, proxies and error trackers."""
    transport = FakeTransport(QUOTE)
    Rephraser(api_key="secret-key", transport=transport).rephrase(QUOTE)

    url, kwargs = transport.calls[0]

    assert "secret-key" not in url
    assert kwargs["headers"]["Authorization"] == "Bearer secret-key"


def test_empty_text_is_not_sent_anywhere():
    transport = FakeTransport("filler")
    result = Rephraser(api_key="k", transport=transport).rephrase("   ")

    assert result == "   "
    assert transport.calls == []


# ---------- a rewording that is only a rewording is accepted ----------


def test_a_faithful_rewording_reaches_the_buyer():
    """The feature has to actually do something, or it is dead weight."""
    better = (
        "That build works out at ₦31,000, one-off. It puts the AI Sales "
        "Representative on your website, handles up to 2,000 conversations a "
        "month, with no integrations. Want me to send the payment link?"
    )

    assert rephraser_returning(better).rephrase(QUOTE) == better


def test_reformatting_a_number_is_not_changing_it():
    """"2,000" and "2000" are the same figure; rejecting that wastes the call."""
    original = "Up to 2,000 conversations a month. Sound right?"
    candidate = "Up to 2000 conversations a month. Does that sound right?"

    assert disagreement(original, candidate) is None


def test_surrounding_quotes_are_stripped_rather_than_rejected():
    """A formatting habit, not a change of meaning."""
    result = rephraser_returning(f'"{QUOTE}"').rephrase(QUOTE)

    assert result == QUOTE


# ---------- the attacks ----------


def test_an_invented_discount_is_refused():
    """The attack this whole module is built around.

    Every original fact survives, which is why a one-directional check would
    pass it, and the buyer would be quoted a price nobody authorised.
    """
    attack = (
        "That build comes to ₦31,000 as a one-off — but I can do ₦20,000 for "
        "you this week. That covers the AI Sales Representative on your "
        "website, up to 2,000 conversations a month and no integrations. Shall "
        "I set up the payment link?"
    )

    assert disagreement(QUOTE, attack) is not None
    assert rephraser_returning(attack).rephrase(QUOTE) == QUOTE


def test_a_dropped_price_is_refused():
    attack = (
        "That's all sorted. It covers the AI Sales Representative on your "
        "website, up to 2,000 conversations a month and no integrations. Shall "
        "I set up the payment link?"
    )

    assert disagreement(QUOTE, attack) is not None


def test_a_changed_price_is_refused():
    attack = QUOTE.replace("₦31,000", "₦13,000")

    assert disagreement(QUOTE, attack) is not None
    assert rephraser_returning(attack).rephrase(QUOTE) == QUOTE


def test_a_rounded_price_is_refused():
    """"about ₦30,000" is friendlier and is not the price."""
    attack = QUOTE.replace("₦31,000", "about ₦30,000")

    assert disagreement(QUOTE, attack) is not None


def test_a_changed_volume_is_refused():
    """The buyer would be billed for a band they were never quoted."""
    attack = QUOTE.replace("2,000", "5,000")

    assert disagreement(QUOTE, attack) is not None


def test_a_product_we_did_not_offer_cannot_be_added():
    """Nera claiming to build something this reply never mentioned."""
    attack = QUOTE.replace(
        "the AI Sales Representative",
        "the AI Sales Representative and the AI Support Agent",
    )

    assert disagreement(QUOTE, attack) is not None
    assert rephraser_returning(attack).rephrase(QUOTE) == QUOTE


def test_a_product_the_buyer_was_offered_cannot_be_dropped():
    both = (
        "Two things then: the AI Sales Representative and the AI Support "
        "Agent. Together that is ₦57,000. Shall I send the link?"
    )
    attack = both.replace(" and the AI Support Agent", "")

    assert disagreement(both, attack) is not None


@pytest.mark.parametrize(
    "promise",
    [
        "It comes with a full refund if you are not happy.",
        "That is guaranteed.",
        "Setup is free.",
        "It handles anything your customers ask.",
        "Support is 24/7.",
        "I can tailor it however you like.",
        "It works instantly.",
        "That is the cheapest you will find.",
    ],
)
def test_a_commitment_the_reply_never_made_is_refused(promise):
    """The failure fact-checking cannot see.

    None of these change a number or a product name. All of them are things a
    business would have to honour, written by a model.
    """
    attack = f"{QUOTE} {promise}"

    assert disagreement(QUOTE, attack) is not None


def test_capability_inflation_is_refused():
    """A rewrite that is fluent, fact-clean and a bigger claim.

    "answers questions from your own material" is a bounded promise we keep.
    "handles anything your customers need" is not, and it contains no figure and
    no new product name — the absolutes are what catch it.
    """
    original = (
        "The AI Support Agent answers questions from your own material and "
        "hands anything commercial straight to you. Shall I price it?"
    )
    attack = (
        "The AI Support Agent completely handles everything your customers "
        "need, 24/7. Shall I price it?"
    )

    assert disagreement(original, attack) is not None


def test_a_commitment_already_in_the_reply_may_stay():
    """The guard is on *introducing* one, not on the word existing.

    Nera's own refusal copy says "pricing isn't mine to change" and mentions the
    discount that was asked for. If the guard were absolute, the copy that most
    needs rewording would be the copy that could never be reworded.
    """
    refusal = (
        "Pricing isn't mine to change — I quote from our published figures "
        "only. I can't offer a discount on the spot, but I'll put the request "
        "to the team. What's the best email to reach you on?"
    )
    reworded = (
        "Pricing isn't mine to move — I quote our published figures and "
        "nothing else. A discount isn't mine to give, but I'll put it to the "
        "team today. What's the best email for you?"
    )

    assert disagreement(refusal, reworded) is None


def test_a_refusal_cannot_be_reworded_into_an_offer():
    """The single most expensive thing this could get wrong."""
    refusal = (
        "Pricing isn't mine to change — I quote from our published figures "
        "only. What's the best email to reach you on?"
    )
    attack = (
        "I can definitely sort out a discount for you — pricing is flexible. "
        "What's the best email to reach you on?"
    )

    assert disagreement(refusal, attack) is not None


def test_a_dropped_question_is_refused():
    """The intake advances by asking. A reply with nothing to answer stalls it."""
    attack = (
        "That build comes to ₦31,000 as a one-off, covering the AI Sales "
        "Representative on your website, up to 2,000 conversations a month "
        "and no integrations. I will set up the payment link."
    )

    assert disagreement(QUOTE, attack) is not None


def test_a_changed_quote_reference_is_refused():
    """A reference off by one character is a reference nobody can find."""
    original = "Your quote reference is qt_a1b2c3d4. Keep it handy — shall I go on?"
    attack = "Your quote reference is qt_a1b2c3d5. Keep it handy — shall I go on?"

    assert disagreement(original, attack) is not None


def test_an_invented_email_or_link_is_refused():
    original = "Reach us at hello@nekosales.ai — is that clear?"

    assert disagreement(original, "Reach us at support@nekosales.ai — clear?") is not None
    assert disagreement(original, "Head to https://evil.example — clear?") is not None


def test_the_model_answering_the_instruction_is_refused():
    """"Here is the rewritten message:" preserves every fact and is not a reply."""
    for preamble in (
        f"Here is the rewritten message:\n{QUOTE}",
        f"Sure! Here's a friendlier version:\n{QUOTE}",
        f"Option 1:\n{QUOTE}",
    ):
        assert disagreement(QUOTE, preamble) is not None


def test_an_essay_is_refused():
    attack = QUOTE + " " + ("Let me tell you more about our approach. " * 12)

    assert disagreement(QUOTE, attack) is not None


def test_a_fragment_is_refused():
    assert disagreement(QUOTE, "₦31,000?") is not None


def test_empty_output_is_refused():
    assert disagreement(QUOTE, "") is not None
    assert disagreement(QUOTE, "   ") is not None
    assert rephraser_returning("").rephrase(QUOTE) == QUOTE


# ---------- the model being unavailable is not an error ----------


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ConnectTimeout("timed out"),
        httpx.ReadTimeout("too slow"),
        httpx.ConnectError("no route"),
        RuntimeError("something unexpected"),
    ],
)
def test_any_failure_ships_the_composed_text(failure):
    """A buyer waiting on a chat reply is better served by plain wording."""
    rephraser = Rephraser(api_key="k", transport=FakeTransport(raises=failure))

    assert rephraser.rephrase(QUOTE) == QUOTE


@pytest.mark.parametrize("status", [400, 401, 429, 500, 503])
def test_a_refused_call_ships_the_composed_text(status):
    assert rephraser_returning(QUOTE, status=status).rephrase(QUOTE) == QUOTE


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"choices": []},
        {"choices": [{}]},
        {"choices": [{"message": {}}]},
        {"choices": [{"message": {"content": None}}]},
        {"error": {"message": "rate limited"}},
    ],
)
def test_an_unreadable_response_ships_the_composed_text(payload):
    """Malformed JSON must not become an exception on a visitor's turn."""
    rephraser = Rephraser(api_key="k", transport=FakeTransport(payload=payload))

    assert rephraser.rephrase(QUOTE) == QUOTE


def test_the_module_level_helper_needs_no_construction():
    assert rephrase(QUOTE, rephraser=rephraser_returning(QUOTE)) == QUOTE


# ---------- what the facts actually are ----------


def test_money_is_one_fact_and_not_also_two_numbers():
    """Without this, "₦31,000" and "31,000 conversations" look identical."""
    facts = extract_facts("₦31,000 for 2,000 conversations")

    assert facts.money == ("₦31000",)
    assert facts.numbers == ("2000",)


def test_products_are_read_from_the_catalog():
    """A product added to pricing is guarded here without anyone editing this."""
    joined = " ".join(PRODUCT_NAMES.values())
    facts = extract_facts(f"We build the {joined}.")

    assert facts.products == frozenset(PRODUCT_NAMES.values())


def test_a_question_is_recorded_as_one():
    assert extract_facts("Shall I go on?").asks_a_question is True
    assert extract_facts("I will go on.").asks_a_question is False


# ---------- wired into the one path every channel uses ----------
#
# The verifier being correct is half of it. The other half is that it is actually
# in the way — and in *one* place, because a rephraser wired per channel is three
# voices and three sets of guards.


class ReweavingTransport:
    """Returns the message it was given, with one harmless substitution.

    A fake that echoes verbatim would pass every assertion here without proving
    the rephrasing reached the buyer, so this changes something visible while
    touching no fact.
    """

    def __init__(self, find, replace):
        self._find = find
        self._replace = replace
        self.calls = 0

    def post(self, url, **kwargs):
        self.calls += 1
        original = kwargs["json"]["messages"][-1]["content"]
        reworded = original.replace(self._find, self._replace)

        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": reworded}}]},
            request=httpx.Request("POST", url),
        )


@pytest.fixture
def storefront(db):
    from app.config.settings import settings
    from app.models.organization import Organization

    org = Organization(name="NekoSalesAI", slug=settings.STOREFRONT_ORG_SLUG)
    db.add(org)
    db.commit()
    db.refresh(org)

    return org


def conversation_service(db, transport):
    from app.sales.service import ConversationService

    return ConversationService(
        db, rephraser=Rephraser(api_key="k", transport=transport)
    )


def test_what_is_stored_is_what_the_buyer_read(db, storefront):
    """A transcript that disagrees with the conversation is worse than none.

    If the composed text were stored while the buyer read the reworded version,
    every later dispute about what Nera said would be unanswerable — and the
    approval queue a human reviews would be showing them the wrong words.
    """
    transport = ReweavingTransport("Tell me", "Talk me through")
    service = conversation_service(db, transport)

    conversation = service.start(storefront.id)
    message = service.handle_visitor_message(conversation, "hello there")

    assert transport.calls == 1
    assert "Talk me through" in message.body

    from app.models.conversation import Message

    stored = db.query(Message).order_by(Message.id.desc()).first()
    assert stored.body == message.body


def test_a_rejected_rewording_stores_the_composed_text(db, storefront):
    """The fallback, at the layer that persists rather than in isolation."""
    transport = FakeTransport("Actually, everything is free. Interested?")
    service = conversation_service(db, transport)

    conversation = service.start(storefront.id)
    message = service.handle_visitor_message(conversation, "hello there")

    assert "free" not in message.body.lower()


def test_a_reworded_quote_still_names_the_figure_that_was_stored(db, storefront):
    """The one that would cost money.

    The reply carries a computed total and a quote row is issued behind it. If
    rephrasing could move the figure, the buyer would read one price and the
    checkout would re-derive another — so this walks the whole intake with the
    rephraser live and checks the two still agree.
    """
    from app.models.conversation import Conversation
    from app.pricing.quotes import QuoteService, reference_from_plan_code
    from tests.test_checkout import INTAKE_ANSWERS

    service = conversation_service(
        db, ReweavingTransport("Shall I", "Do you want me to")
    )

    conversation = service.start(storefront.id)
    for answer in INTAKE_ANSWERS:
        last = service.handle_visitor_message(conversation, answer)

    db.refresh(conversation)
    reference = reference_from_plan_code(conversation.interested_plan_code)
    assert reference, "the intake did not reach a quote"

    _row, recomputed = QuoteService(db).recompute(reference)

    assert recomputed.display_total in last.body
    assert db.query(Conversation).one().stage == "ready_to_buy"


def test_rephrasing_cannot_change_where_the_conversation_got_to(db, storefront):
    """Stage, scope and quote are derived before a model is consulted.

    Asserted by walking the same intake twice — once with a rephraser that
    rewrites every reply, once with none — and comparing the state left behind.
    Same stage, same scope, same price: the model touched the wording and nothing
    else.
    """
    from app.models.conversation import Conversation
    from app.sales.service import ConversationService
    from tests.test_checkout import INTAKE_ANSWERS

    def walk(service):
        conversation = service.start(storefront.id)
        for answer in INTAKE_ANSWERS:
            service.handle_visitor_message(conversation, answer)
        db.refresh(conversation)
        return conversation.stage, conversation.scope_json

    plain = walk(ConversationService(db, rephraser=Rephraser(api_key="")))
    reworded = walk(
        conversation_service(db, ReweavingTransport("Shall I", "Do you want me to"))
    )

    assert plain == reworded
    assert db.query(Conversation).count() == 2

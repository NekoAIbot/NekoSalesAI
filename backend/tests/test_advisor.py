"""Nera advising a business on what to buy, and selling more than one thing.

Two properties are defended here, and they are the two ways this feature could
be worse than not having it.

**Nothing is offered that does not exist.** The advisor's table of what each
product is for is checked against the pricing engine's catalog, in both
directions. A product the engine can price but the advisor cannot describe fails
here; so does a product the advisor describes that the engine cannot price. That
is what makes "we only ever offer what we actually build" a property of the code
rather than a promise about the copy.

**A buyer who picks two gets two.** Both on the bill, separately priced, and both
actually stood up when they pay. The failure this guards against is the one that
does not look like a failure from the inside: a quote for two agents, a payment
for two agents, one agent delivered, and every internal signal reading "sold".
"""

import json

import pytest

from app.pricing.complexity import (
    CHANNEL_WEB,
    CHANNEL_WHATSAPP,
    DIMENSION_BASE,
    PRODUCT_BASE_MINOR,
    PRODUCT_NAMES,
    PRODUCT_SALES_AGENT,
    PRODUCT_SUPPORT_AGENT,
    PricingError,
    Requirement,
    bundle_name,
    price,
)
from app.pricing.quotes import QuoteService
from app.sales.advisor import (
    FITS,
    advice_text,
    describes_a_business,
    options_text,
    recommend,
)
from app.sales.agent import RULE_ADVICE, RULE_SCOPING, compose_reply
from app.sales.scoping import (
    LEGACY_STEP_PRODUCT,
    QUESTIONS,
    STEP_PRODUCT,
    Scope,
    parse_products,
    product_options,
)

# ---------- the advisor cannot outrun the catalog ----------


def test_every_product_we_can_price_can_be_advised_on():
    """A product added to pricing without being taught to the advisor.

    Without this, adding a product type means Nera can quote for something it
    cannot describe — so the recommendation step silently ignores it and the
    buyer is never offered a thing we built and priced.
    """
    assert set(FITS) == set(PRODUCT_BASE_MINOR)


def test_the_advisor_never_describes_a_product_we_cannot_build():
    """The direction that matters more.

    A ``FITS`` entry with no pricing behind it is Nera offering to build
    something that does not exist — the exact claim this whole design refuses to
    let it make.
    """
    for code in FITS:
        assert code in PRODUCT_NAMES, f"{code} is advised on but has no name"
        assert code in PRODUCT_BASE_MINOR, f"{code} is advised on but has no price"


def test_every_fit_says_what_it_does_and_why():
    """Empty copy would render as a bullet with nothing after the dash."""
    for code, fit in FITS.items():
        assert fit.does.strip(), f"{code} has no description"
        assert fit.because.strip(), f"{code} has no reason"
        assert fit.signals, f"{code} can never be recommended: no signals"


def test_no_copy_hardcodes_how_many_products_there_are():
    """"Which of the two" is a sentence that goes stale on the next product.

    Checked across the option list, the intake question and the advisor's own
    text, because the count leaking into any one of them is Nera telling a buyer
    there are two options while listing three.
    """
    surfaces = [
        product_options(),
        QUESTIONS[STEP_PRODUCT],
        options_text(),
        advice_text(recommend("I run a shop and get lots of questions")),
    ]

    for text in surfaces:
        lowered = text.lower()
        for count in ("the two", "the three", "two options", "three options",
                      "either of the two", "both of the"):
            assert count not in lowered, f"{count!r} is hardcoded in: {text[:80]}"


def test_the_option_list_is_generated_from_the_catalog():
    """Every product appears, named as the engine names it."""
    listing = product_options()

    for name in PRODUCT_NAMES.values():
        assert name in listing


# ---------- reading a business ----------


@pytest.mark.parametrize(
    "description, expected",
    [
        ("I run a food store", (PRODUCT_SALES_AGENT,)),
        ("we sell shoes online", (PRODUCT_SALES_AGENT,)),
        ("I own a boutique in Ikeja", (PRODUCT_SALES_AGENT,)),
        ("my company is a dental clinic", (PRODUCT_SUPPORT_AGENT,)),
        ("we run a school", (PRODUCT_SUPPORT_AGENT,)),
        ("I run a consulting agency", (PRODUCT_SUPPORT_AGENT,)),
    ],
)
def test_a_business_is_read_as_the_products_that_fit_it(description, expected):
    assert recommend(description).recommended == expected


def test_a_business_that_needs_both_is_told_so():
    """A shop that also answers questions genuinely needs both."""
    result = recommend("I run a pharmacy and answer the same questions all day")

    assert result.recommended == (PRODUCT_SALES_AGENT, PRODUCT_SUPPORT_AGENT)
    assert result.is_everything


def test_a_recommendation_records_what_it_was_read_from():
    """The reasoning trail has to name the word, not just the conclusion."""
    result = recommend("I run a food store")

    assert result.matched
    assert len(result.matched) == len(result.recommended)
    assert any("food" in m or "store" in m for m in result.matched)


def test_a_need_we_do_not_build_for_is_named_rather_than_stretched():
    """The case worth getting right.

    Reading "bookkeeping" as close enough to "support" and quoting for it is how
    a business ends up paying for software that does not do the job. An empty
    recommendation is an answer, and it has to survive.
    """
    result = recommend("I need an AI that does my bookkeeping and tax filings")

    assert result.recommended == ()
    assert result.has_advice is False
    assert result.too_vague is False


def test_the_refusal_says_what_we_do_build():
    """Refusing without offering the alternative is just a dead end."""
    body = advice_text(recommend("I need an AI to write my payroll software"))

    assert "right fit" in body
    for name in PRODUCT_NAMES.values():
        assert name in body


@pytest.mark.parametrize("greeting", ["hi", "hello", "yo", "good morning"])
def test_a_greeting_is_not_a_business_description(greeting):
    """Advising on the strength of nothing is guessing dressed as consultancy."""
    assert recommend(greeting).too_vague is True


@pytest.mark.parametrize(
    "asked",
    [
        "what do you build?",
        "what can you offer",
        "what are my options",
        "show me everything",
    ],
)
def test_asking_what_we_have_gets_the_list_not_an_opinion(asked):
    result = recommend(asked)

    assert result.asked_for_options is True
    assert advice_text(result) == options_text()


def test_the_full_list_says_it_is_the_full_list():
    """Two options read as a sample of a larger catalogue unless we say so.

    Letting a buyer assume there is more is the same as claiming there is.
    """
    body = options_text()

    assert "whole list" in body.lower()
    for name in PRODUCT_NAMES.values():
        assert name in body


@pytest.mark.parametrize(
    "text, describes",
    [
        ("I run a food store", True),
        ("we own a pharmacy", True),
        ("my business is a hotel", True),
        ("I'm a dentist", True),
        # A need stated as a need. Without this, "I need an AI that does my
        # bookkeeping" reaches the greeting — "tell me what your business needs
        # and I'll tell you what I'd build" — which reads as yes to a thing we
        # do not build.
        ("I need an AI that does my bookkeeping", True),
        ("we want a chatbot for our restaurant", True),
        ("how much is it?", False),
        ("hi", False),
        ("do you take card?", False),
        ("2000", False),
        # Belongs to the intake, not the advisor: answering a request for a
        # figure with an unasked-for opinion is worse than useless.
        ("I need a quote", False),
    ],
)
def test_only_an_actual_description_gets_advice(text, describes):
    """A pricing question met with an unasked-for opinion is worse than useless.

    "how much is it?" contains no product signal, so if it reached the advisor it
    would come back as "nothing I build fits you" — a refusal invented out of a
    question about price.
    """
    assert describes_a_business(text) is describes


# ---------- picking more than one ----------


@pytest.mark.parametrize(
    "answer, expected",
    [
        ("both", (PRODUCT_SALES_AGENT, PRODUCT_SUPPORT_AGENT)),
        ("both please", (PRODUCT_SALES_AGENT, PRODUCT_SUPPORT_AGENT)),
        ("all of them", (PRODUCT_SALES_AGENT, PRODUCT_SUPPORT_AGENT)),
        ("everything", (PRODUCT_SALES_AGENT, PRODUCT_SUPPORT_AGENT)),
        ("the sales one and the support one", (PRODUCT_SALES_AGENT, PRODUCT_SUPPORT_AGENT)),
        ("sales rep and help desk", (PRODUCT_SALES_AGENT, PRODUCT_SUPPORT_AGENT)),
        ("just sales", (PRODUCT_SALES_AGENT,)),
        ("support please", (PRODUCT_SUPPORT_AGENT,)),
        ("first one", (PRODUCT_SALES_AGENT,)),
        ("second option", (PRODUCT_SUPPORT_AGENT,)),
    ],
)
def test_one_answer_can_name_several_products(answer, expected):
    assert parse_products(answer) == expected


@pytest.mark.parametrize(
    "answer",
    [
        "sales but not support",
        "I need sales, no support agent",
        "just the sales one, without the support desk",
    ],
)
def test_a_negated_product_is_not_added_to_the_order(answer):
    """"I don't need support" contains the word that would add a support agent.

    Reading it as a request would put a product on the bill the buyer explicitly
    declined — and they would find out at the payment page.
    """
    assert parse_products(answer) == (PRODUCT_SALES_AGENT,)


def test_an_unreadable_answer_is_not_read_as_wanting_nothing():
    """None means ask again. It never means "they chose none of it"."""
    assert parse_products("banana") is None
    assert parse_products("") is None


def test_the_order_products_are_named_in_does_not_change_the_build():
    """"sales and support" and "support and sales" are the same purchase."""
    one = parse_products("sales and support")
    other = parse_products("support and sales")

    assert one == other


# ---------- two products, one bill ----------


def test_each_product_carries_its_own_base_line():
    """A buyer taking two sees what each costs, not one lump."""
    quote = price(
        Requirement(products=(PRODUCT_SALES_AGENT, PRODUCT_SUPPORT_AGENT))
    )

    bases = [i for i in quote.line_items if i.dimension == DIMENSION_BASE]

    assert len(bases) == 2
    assert [i.amount_minor for i in bases] == [
        PRODUCT_BASE_MINOR[PRODUCT_SALES_AGENT],
        PRODUCT_BASE_MINOR[PRODUCT_SUPPORT_AGENT],
    ]


def test_two_products_cost_the_sum_of_their_bases():
    quote = price(
        Requirement(products=(PRODUCT_SALES_AGENT, PRODUCT_SUPPORT_AGENT))
    )

    assert quote.total_minor == (
        PRODUCT_BASE_MINOR[PRODUCT_SALES_AGENT]
        + PRODUCT_BASE_MINOR[PRODUCT_SUPPORT_AGENT]
    )


def test_scope_is_charged_once_however_many_products():
    """Two agents on one WhatsApp number is one integration to build.

    Charging the channel per product would be billing twice for work done once —
    and a buyer who checked the arithmetic would be right to call it padding.
    """
    both = price(
        Requirement(
            products=(PRODUCT_SALES_AGENT, PRODUCT_SUPPORT_AGENT),
            channels=(CHANNEL_WEB, CHANNEL_WHATSAPP),
        )
    )
    one = price(
        Requirement(
            products=(PRODUCT_SALES_AGENT,),
            channels=(CHANNEL_WEB, CHANNEL_WHATSAPP),
        )
    )

    difference = both.total_minor - one.total_minor

    assert difference == PRODUCT_BASE_MINOR[PRODUCT_SUPPORT_AGENT]


def test_the_bundle_is_named_after_what_is_in_it():
    """This name lands on a receipt and a card statement.

    "Growth Pack" tells the buyer nothing about what they bought; two product
    names tell them exactly.
    """
    name = bundle_name((PRODUCT_SALES_AGENT, PRODUCT_SUPPORT_AGENT))

    assert PRODUCT_NAMES[PRODUCT_SALES_AGENT] in name
    assert PRODUCT_NAMES[PRODUCT_SUPPORT_AGENT] in name


def test_asking_for_the_same_product_twice_is_one_product():
    """A typo, not two builds."""
    quote = price(
        Requirement(products=(PRODUCT_SALES_AGENT, PRODUCT_SALES_AGENT))
    )

    assert quote.products == (PRODUCT_SALES_AGENT,)
    assert quote.total_minor == PRODUCT_BASE_MINOR[PRODUCT_SALES_AGENT]


def test_the_products_are_stored_in_catalog_order_whichever_way_they_are_asked():
    """The same two products must price identically either way round."""
    forwards = price(
        Requirement(products=(PRODUCT_SALES_AGENT, PRODUCT_SUPPORT_AGENT))
    )
    backwards = price(
        Requirement(products=(PRODUCT_SUPPORT_AGENT, PRODUCT_SALES_AGENT))
    )

    assert forwards.products == backwards.products
    assert forwards.total_minor == backwards.total_minor
    assert forwards.product_name == backwards.product_name


def test_a_build_for_no_product_is_refused():
    """Zero products has no base, so it would price at the scope alone.

    A quote for channels and volume with nothing to run on them is a bill for
    infrastructure the buyer cannot use.
    """
    with pytest.raises(PricingError):
        Requirement(product_type="", products=())


def test_a_product_we_do_not_build_is_refused_even_alongside_one_we_do():
    """The unknown one must not be quietly dropped from a valid-looking order."""
    with pytest.raises(PricingError):
        Requirement(products=(PRODUCT_SALES_AGENT, "mind_reader"))


def test_the_single_product_spelling_still_works():
    """Every existing caller passes one product by name."""
    requirement = Requirement(product_type=PRODUCT_SUPPORT_AGENT)

    assert requirement.products == (PRODUCT_SUPPORT_AGENT,)
    assert requirement.product_type == PRODUCT_SUPPORT_AGENT


def test_the_two_spellings_cannot_disagree():
    """``product_type`` is maintained as the first of ``products``."""
    requirement = Requirement(
        products=(PRODUCT_SALES_AGENT, PRODUCT_SUPPORT_AGENT)
    )

    assert requirement.product_type == requirement.products[0]


# ---------- surviving storage ----------


def test_a_two_product_quote_re_prices_to_the_same_figure(db):
    """The checkout re-prices rather than trusting the row.

    If the second product did not survive the round trip, the buyer would be
    charged for one agent at the payment page having agreed to two.
    """
    service = QuoteService(db)
    requirement = Requirement(
        products=(PRODUCT_SALES_AGENT, PRODUCT_SUPPORT_AGENT)
    )

    quote = service.issue(requirement)
    _row, recomputed = service.recompute(quote.reference)

    assert recomputed.products == (PRODUCT_SALES_AGENT, PRODUCT_SUPPORT_AGENT)
    assert recomputed.total_minor == price(requirement).total_minor


def test_a_scope_with_two_products_survives_the_conversation_row():
    """A messenger carries no session; the scope column is the whole memory."""
    scope = Scope(
        products=(PRODUCT_SALES_AGENT, PRODUCT_SUPPORT_AGENT),
        channels=(CHANNEL_WEB,),
        monthly_conversations=500,
        integrations=0,
    )

    restored = Scope.from_json(scope.to_json())

    assert restored.products == scope.products
    assert restored.to_requirement().products == scope.products


def test_a_scope_stored_before_multi_select_still_loads():
    """A conversation that was mid-intake when this shipped.

    Losing the answer would mean asking the product question again, which reads
    to the buyer as the agent forgetting what they just said.
    """
    legacy = json.dumps(
        {
            LEGACY_STEP_PRODUCT: PRODUCT_SUPPORT_AGENT,
            "channels": [CHANNEL_WEB],
            "monthly_conversations": 500,
            "integrations": 0,
        }
    )

    restored = Scope.from_json(legacy)

    assert restored.products == (PRODUCT_SUPPORT_AGENT,)
    assert restored.is_complete


def test_a_stored_scope_naming_a_product_we_dropped_is_ignored():
    """Junk reads as unanswered, so the buyer is asked rather than crashed at."""
    restored = Scope.from_json(json.dumps({STEP_PRODUCT: ["mind_reader"]}))

    assert restored.products is None


# ---------- the agent's own turn ----------


def test_describing_a_business_gets_advice_before_any_price():
    """The point of the whole feature: advice first, figures after."""
    reply = compose_reply("I run a food store", "greeting", scope=Scope())

    assert reply.reasoning.rule == RULE_ADVICE
    assert "₦" not in reply.body


def test_the_advice_does_not_choose_for_the_buyer():
    """A recommendation is not a selection.

    Writing their answer into the scope would put a product on the order nobody
    picked, and the buyer would meet it at the payment page.
    """
    reply = compose_reply("I run a food store", "greeting", scope=Scope())

    assert reply.scope is not None
    assert reply.scope.products is None


def test_a_business_we_cannot_help_is_escalated():
    """Worth a human's attention, and not worth a stretched product."""
    reply = compose_reply(
        "I need an AI that does my bookkeeping", "greeting", scope=Scope()
    )

    assert reply.reasoning.escalated is True
    assert reply.needs_approval is True


def test_advice_names_the_signal_in_its_reasoning():
    reply = compose_reply("I run a pharmacy", "greeting", scope=Scope())

    assert any("recommended" in s for s in reply.reasoning.signals)


def test_a_price_question_is_never_answered_with_advice():
    """It has to reach the intake, not the advisor."""
    reply = compose_reply("how much is it?", "greeting", scope=Scope())

    assert reply.reasoning.rule == RULE_SCOPING


def test_a_description_offered_mid_intake_does_not_restart_the_flow():
    """"we're a clinic, by the way" is context, not a request to start over."""
    mid = Scope(products=(PRODUCT_SALES_AGENT,))

    reply = compose_reply("we run a clinic actually", "qualified", scope=mid)

    assert reply.reasoning.rule != RULE_ADVICE


def test_the_advisor_never_names_a_product_outside_the_catalog():
    """Whatever a buyer describes, the answer only ever offers what exists."""
    described = [
        "I run a food store",
        "we are a hospital",
        "I need an AI to do my taxes",
        "what do you build?",
        "hi",
    ]

    allowed = set(PRODUCT_NAMES.values())

    for text in described:
        body = advice_text(recommend(text))

        # Every capitalised "AI ..." phrase in the copy must be a real product.
        for name in ("AI Sales Representative", "AI Support Agent"):
            if name in body:
                assert name in allowed


# ---------- what real buyers actually typed ----------
#
# Every string below is verbatim from live traffic, and every one of them was
# answered wrongly. Two of the senders were strangers who had found the bot an
# hour earlier; both were escalated to a human on their first message, which is
# the failure that costs the sale rather than merely reading badly. The
# phrasings are kept exactly as typed — apostrophes missing, capitalisation
# arbitrary — because tidying them up is how they passed in the first place.


ESCALATED_ON_TURN_ONE = [
    # The progressive form. "I run a food store" matched the verb list and
    # "I'm running a food store" matched nothing, so the same sentence in the
    # tense people actually use fell through to the don't-know fallback.
    "Im running a food store",
    "I'm running a food store",
    # A trade with no keyword in our signal lists. Nothing about a bakery says
    # it cannot use a sales rep — only our vocabulary was silent — but the empty
    # recommendation was read as "we build nothing for this business".
    "i have a bakery",
    "my business is a barbershop",
    # The answer the greeting asks for. It asks what the business needs done,
    # and then escalated the reply.
    "Profit and more customers of course",
    "I need more customers",
    # Typed into the website chat. An AI Sales Representative for a shop, on two
    # channels, with a volume band — the most ordinary order this product takes,
    # with more detail up front than most buyers give — and it was told we did
    # not think our products were the right fit. One adjective between "my" and
    # "business" was the whole cause.
    "AI for my clothing business, 2k conversations/month on WhatsApp and Telegram",
]


@pytest.mark.parametrize("text", ESCALATED_ON_TURN_ONE)
def test_an_ordinary_first_message_is_never_escalated(text):
    """The one property all four live defects violated.

    A buyer's opening line is answered by Nera or asked about by Nera. It does
    not go to a human — there is nothing here a human answers better than the
    next turn does, and a stranger handed to a person on their first message
    does not come back.
    """
    reply = compose_reply(text, "greeting", scope=Scope())

    assert reply.reasoning.escalated is False
    assert reply.needs_approval is False


@pytest.mark.parametrize("text", ESCALATED_ON_TURN_ONE)
def test_an_ordinary_first_message_is_never_refused(text):
    """And is never told we build nothing for them.

    Distinct from the escalation above and worth its own assertion: the refusal
    copy is the most damaging thing in the module to send to the wrong person,
    and a bakery was getting it.
    """
    body = compose_reply(text, "greeting", scope=Scope()).body

    assert "the right fit" not in body


@pytest.mark.parametrize("text", ESCALATED_ON_TURN_ONE)
def test_an_ordinary_first_message_reaches_the_advisor(text):
    """Answered or asked about — never a dead end.

    Every one of these landed on the don't-know fallback, which apologises and
    fetches a person. Asserting the rule rather than the prose because the rule
    is the decision: the advisor either recommends something or asks for the
    detail it is missing, and both are a conversation continuing.
    """
    reply = compose_reply(text, "greeting", scope=Scope())

    assert reply.reasoning.rule == RULE_ADVICE


# Descriptions that happen to contain a word the product parser knows. Read as
# a *selection*, so the intake answered "Noted." and moved to channels with a
# product on the scope the buyer never named.
DESCRIBES_BUT_DOES_NOT_CHOOSE = [
    "we sell shoes online",
    "I sell clothes in Lagos",
    "we run a pharmacy and sell drugs",
]


@pytest.mark.parametrize("text", DESCRIBES_BUT_DOES_NOT_CHOOSE)
def test_a_description_containing_a_product_word_is_not_a_selection(text):
    """"we sell shoes online" is a shop, not an order for a sales rep.

    The keyword is incidental to the sentence, and treating it as an answer put
    a product on the scope nobody chose — which the buyer would next meet at the
    payment page, priced.
    """
    reply = compose_reply(text, "greeting", scope=Scope())

    assert reply.scope is not None
    assert reply.scope.products is None


@pytest.mark.parametrize("text", DESCRIBES_BUT_DOES_NOT_CHOOSE)
def test_a_description_containing_a_product_word_gets_advice(text):
    """And is answered by the advisor, whose turn it was."""
    reply = compose_reply(text, "greeting", scope=Scope())

    assert reply.reasoning.rule == RULE_ADVICE


# ---------- the refusal still has to work ----------


def test_a_named_need_we_do_not_build_is_still_refused():
    """The guard on the fix above.

    Separating "not enough detail yet" from "we do not build that" is only worth
    doing if the second half keeps working. A buyer who names the software they
    want and gets a polite question instead of an honest no has been sold a
    hope, and will find out after paying.
    """
    reply = compose_reply(
        "I need an AI that does my bookkeeping", "greeting", scope=Scope()
    )

    assert reply.reasoning.escalated is True
    assert reply.needs_approval is True
    assert "the right fit" in reply.body


def test_a_trade_we_have_no_keyword_for_is_not_a_refusal():
    """The same shape, the other outcome, at the advisor level.

    ``unmet_need`` is the thing that separates them, and it is not "the
    recommendation is empty" — both of these are empty.

    "i have a bakery" used to be the example here, and is now in the vocabulary:
    a bakery takes orders, so recommending the sales rep beats asking which of
    the two they want. The property still needs a trade we genuinely have no word
    for, because there will always be one.
    """
    assert recommend("I need an AI that does my bookkeeping").unmet_need is True
    assert recommend("i run a survey and mapping outfit").unmet_need is False
    assert recommend("i run a survey and mapping outfit").needs_more_detail is True


def test_a_trade_we_do_have_a_keyword_for_is_recommended_on():
    """The other half: a gap closed is a turn saved.

    A bakery, a salon and a clothes shop all sell things to people who ask what
    they cost. Asking "which of the two do you want?" of someone who has already
    said is the reading that made a real visitor give up.
    """
    for description in ("i have a bakery", "AI for my clothing business"):
        result = recommend(description)

        assert result.recommended == (PRODUCT_SALES_AGENT,), description
        assert result.needs_more_detail is False, description


def test_naming_a_product_is_still_read_as_choosing_it():
    """The advisor must not hijack an answer.

    "I need an AI sales representative" names a need *and* a product we build.
    Recommending what they just asked for costs them a turn and reads as not
    listening.
    """
    reply = compose_reply(
        "I want to buy an AI sales representative", "greeting", scope=Scope()
    )

    assert reply.scope is not None
    assert reply.scope.products == (PRODUCT_SALES_AGENT,)


def test_a_bare_selection_is_still_read_as_choosing_it():
    """The short form, which names no business at all."""
    reply = compose_reply("the sales one", "greeting", scope=Scope())

    assert reply.scope is not None
    assert reply.scope.products == (PRODUCT_SALES_AGENT,)


def test_a_progressive_description_reaches_the_advisor():
    """Defect A at the predicate level, where the cause was."""
    assert describes_a_business("Im running a food store") is True
    assert describes_a_business("I'm running a food store") is True
    assert describes_a_business("we're setting up a delivery service") is True


def test_wanting_an_outcome_counts_as_telling_us_something():
    """Defect C at the predicate level.

    Thin evidence, deliberately: it earns the advisor's turn, not a
    recommendation. What it must not earn is silence.
    """
    assert describes_a_business("Profit and more customers of course") is True
    assert describes_a_business("I need more customers") is True
    assert describes_a_business("we want to stop losing sales") is True


def test_a_pricing_question_is_not_a_business_description():
    """The boundary that keeps the advisor from answering everything.

    "how much is it" is three words with no product signal in them. Reading it
    as a business would invent a refusal out of a pricing question.
    """
    assert describes_a_business("how much is it") is False
    assert describes_a_business("hi") is False
    assert describes_a_business("the sales one") is False


# ---------- Bug 5: one adjective ----------


@pytest.mark.parametrize(
    "text",
    [
        "AI for my clothing business",
        "AI for my clothing business, 2k conversations/month on WhatsApp "
        "and Telegram",
        "chatbot for my online store",
        "something for our small company",
        "AI for my restaurant",
        "I want AI for my salon",
    ],
)
def test_a_word_between_the_possessive_and_the_noun_still_describes_a_business(
    text,
):
    """The predicate, where Bug 5 actually was.

    The rule wanted "my business" and "our shop" adjacent. Real buyers write "my
    clothing business" and "our online store", and the trade is often the only
    noun there at all — "AI for my restaurant". Every one of those fell past this
    module to the escalation fallback.
    """
    assert describes_a_business(text) is True


def test_a_shop_that_sells_a_thing_we_had_no_word_for_is_still_a_shop():
    """And gets a recommendation, not "tell me more".

    The sentence said people buy clothes from them. Our vocabulary happened not
    to contain "clothing", and a gap in our vocabulary is not a business we
    cannot help.
    """
    result = recommend("AI for my clothing business")

    assert result.recommended == (PRODUCT_SALES_AGENT,)
    assert result.needs_more_detail is False
    assert result.unmet_need is False


def test_the_whole_live_message_is_priced_rather_than_refused():
    """End to end at the engine, in the buyer's exact words.

    The reply a real visitor got began "I don't think my products are the right
    fit" and offered to pass them to a person. Asserting the rule and the two
    flags rather than the prose: the decision is what was wrong.
    """
    reply = compose_reply(
        "AI for my clothing business, 2k conversations/month on WhatsApp "
        "and Telegram",
        "greeting",
        scope=Scope(),
    )

    assert reply.reasoning.rule == RULE_ADVICE
    assert reply.reasoning.escalated is False
    assert reply.needs_approval is False
    assert "the right fit" not in reply.body

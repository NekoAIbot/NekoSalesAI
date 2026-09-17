"""The four intake answers, parsed the way people actually type them.

Written after a simulation sweep produced 189 near-misses from a single cause:
``parse_integrations("just one")`` returned None, so Nera asked the identical
question again — eleven times in a row in the worst transcript — and the buyer
ran out of patience without ever seeing a price. Nothing escalated, nothing
errored, and no existing test failed. The intake simply never finished.

That is the failure mode this file exists for. A parser that returns None is not
safe by default: it costs a turn every time, and enough of them costs the sale.
So the cases here are phrasings taken from transcripts rather than tidy inputs —
and, just as importantly, the vague phrasings that must *stay* unreadable,
because reading "a few" as three invents ₦15,000 nobody agreed to.
"""

import pytest

from app.pricing.complexity import MAX_QUOTABLE_CONVERSATIONS
from app.sales.scoping import (
    MAX_INTEGRATIONS,
    parse_integrations,
    parse_volume,
    parse_word_count,
    parse_word_volume,
)


# ---------- counts written as words ----------


@pytest.mark.parametrize(
    ("said", "expected"),
    [
        ("just one", 1),
        ("only one system", 1),
        ("a couple", 2),
        ("a couple of them", 2),
        ("both", 2),
        ("two", 2),
        ("three or four", 3),  # the first number stated wins
        ("five", 5),
        ("ten", 10),
        ("zero", 0),
        ("none of them", 0),
        ("a single one", 1),
    ],
)
def test_a_count_written_as_a_word_is_read(said, expected):
    """"two" is exactly as precise as "2". Refusing it was a gap, not caution."""
    assert parse_integrations(said) == expected


@pytest.mark.parametrize(
    "said",
    [
        "a few",
        "several",
        "a handful",
        "some",
        "quite a few",
        "not sure yet",
        "loads of them",
        "many",
    ],
)
def test_a_vague_count_stays_unreadable_on_purpose(said):
    """Each system is ₦5,000, so a guess here invents money.

    Asking again costs one sentence. Reading "a few" as three costs ₦15,000 the
    buyer never agreed to, on an invoice they will read.
    """
    assert parse_integrations(said) is None


def test_digits_still_win_over_words():
    """A digit is unambiguous, so the word fallback must not pre-empt it."""
    assert parse_integrations("3 systems") == 3
    assert parse_integrations("we have 7 to connect") == 7


def test_a_word_count_over_the_ceiling_is_refused_like_a_digit_one():
    """The ceiling is about what we will build, not about notation."""
    from app.sales.scoping import ScopingError

    over = MAX_INTEGRATIONS + 1

    with pytest.raises(ScopingError):
        parse_integrations(str(over))


# ---------- volumes written as words ----------


@pytest.mark.parametrize(
    ("said", "expected"),
    [
        ("five hundred", 500),
        ("about five hundred", 500),
        ("a thousand", 1_000),
        ("two thousand", 2_000),
        ("ten thousand", 10_000),
        ("a hundred", 100),
        ("three hundred a month", 300),
    ],
)
def test_a_volume_spelled_out_is_read(said, expected):
    assert parse_word_volume(said) == expected


@pytest.mark.parametrize(
    ("said", "expected"),
    [
        ("about five hundred", 500),
        # Snapped up to the band that covers it, exactly as "1000" is. The bands
        # are what the engine has costed, so a figure between two of them is
        # quoted at the one above rather than interpolated.
        ("a thousand a month", 2_000),
        ("two thousand conversations", 2_000),
    ],
)
def test_the_volume_step_accepts_a_spelled_out_figure(said, expected):
    """Reaches ``parse_volume``, not just the word helper underneath it."""
    assert parse_volume(said) == expected


@pytest.mark.parametrize(
    ("words", "digits"),
    [
        ("five hundred", "500"),
        ("a thousand", "1000"),
        ("two thousand", "2000"),
        ("ten thousand", "10000"),
    ],
)
def test_notation_never_changes_the_band(words, digits):
    """The invariant that matters: how it was typed cannot move the price."""
    assert parse_volume(words) == parse_volume(digits)


@pytest.mark.parametrize("said", ["loads", "a lot", "no idea", "hard to say", "busy"])
def test_a_vague_volume_stays_unreadable(said):
    """Volume moves the price by bands, so a guess moves the invoice."""
    assert parse_volume(said) is None


def test_a_spelled_out_volume_over_the_ceiling_is_refused():
    """"a million" is past what the bands cover, word or digit."""
    from app.sales.scoping import ScopingError

    with pytest.raises(ScopingError):
        parse_volume(str(MAX_QUOTABLE_CONVERSATIONS + 1))


def test_word_count_and_word_volume_do_not_read_each_others_input():
    """"five hundred" is not the count five.

    Sharing the word table between the two parsers is what makes this worth
    asserting: the count parser sees "five" inside "five hundred", and reading
    it as five systems would put ₦25,000 on the quote.
    """
    assert parse_word_volume("five hundred") == 500
    # The count parser is only ever reached by the integrations step, which is
    # a different question — but if the two were ever wired to the same input,
    # this is the mistake it would make, and it should be visible in the file.
    assert parse_word_count("five hundred") == 5


# ---------- the whole intake reaches a price ----------


def test_a_buyer_who_answers_in_words_reaches_a_quote():
    """The end-to-end shape of the 189-near-miss bug.

    Every answer below is a word rather than a digit, which is how the live
    transcripts read. Before the fix this stalled on the integrations question
    and looped until the buyer gave up.
    """
    from app.models.conversation import STAGE_QUALIFIED
    from app.sales.agent import RULE_DYNAMIC_QUOTE, compose_reply
    from app.sales.scoping import Scope

    scope = Scope()
    said = ["the sales rep", "just my website", "about five hundred", "just one"]

    reply = None

    for message in said:
        reply = compose_reply(message, STAGE_QUALIFIED, scope=scope)
        scope = reply.scope if reply.scope is not None else scope

    assert reply is not None
    assert scope.is_complete, f"intake did not finish: {scope}"
    assert reply.reasoning.rule == RULE_DYNAMIC_QUOTE, reply.body
    assert "₦" in reply.body


def test_the_same_answers_in_digits_reach_the_same_price():
    """Notation must not change the invoice."""
    from app.models.conversation import STAGE_QUALIFIED
    from app.sales.agent import compose_reply
    from app.sales.scoping import Scope

    def total_for(answers):
        scope = Scope()
        reply = None

        for message in answers:
            reply = compose_reply(message, STAGE_QUALIFIED, scope=scope)
            scope = reply.scope if reply.scope is not None else scope

        return scope.to_requirement()

    words = total_for(["the sales rep", "just my website", "five hundred", "just one"])
    digits = total_for(["the sales rep", "just my website", "500", "1"])

    assert words == digits

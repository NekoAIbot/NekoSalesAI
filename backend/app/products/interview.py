"""Conversational requirements intake: an interview that fills ``IntakeIn``.

Stage B1 gave the factory a structured form. A form is the right thing to
validate and store, and the wrong thing to hand a customer who has never
thought about billing periods. This module asks one question at a time and
turns the answers into that same form, so there is still exactly one place
where customer text becomes product behaviour.

The parsing is deterministic and narrow, for the same reason the sales agent
is rule-based rather than generative: **no code path turns ambiguous prose
into a number.** If an answer does not clearly contain a price, the interview
re-asks instead of guessing, and a plan the customer never priced is never
invented. The failure mode of a guess here is not a bad sentence — it is a
customer discovering that their AI has been quoting a figure nobody set.

The interview holds no state of its own. The caller submits every answer
collected so far and gets back the next question, so a draft can live in the
client, a database row or a chat transcript without this module changing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.schemas.intake import (
    BILLING_PERIODS,
    SUPPORTED_CURRENCIES,
    IntakeIn,
    PlanIn,
    QuestionAnswerIn,
)

# Field keys the interview collects. Deliberately the names of IntakeIn fields
# so a reader can see which question feeds which part of the product.
STEP_COMPANY_NAME = "company_name"
STEP_DESCRIPTION = "description"
STEP_AGENT_NAME = "agent_name"
STEP_SUPPORT_EMAIL = "support_email"
STEP_PLANS = "plans"
STEP_CAPABILITIES = "capabilities"
STEP_FAQS = "faqs"
STEP_DISCOUNT = "max_auto_discount_percent"

# Answers a customer gives to mean "nothing here". Matched exactly, after
# lowercasing and stripping — a substring match would read "no evening slots"
# as a skip and silently drop a real capability.
SKIP_ANSWERS = frozenset({"", "-", "none", "no", "n/a", "na", "skip", "nothing"})

_CURRENCY_SYMBOLS = {"₦": "NGN", "$": "USD"}

# "Scale and Polish, 18500.50, visit" — name, amount, optional period. Split
# on commas because that is what people type in a chat box, and because it
# keeps the name free of digits we would otherwise have to guess about.
_PLAN_SEPARATOR = ","

# A bare price token: optional symbol or code, then digits with optional
# decimals. No thousands separators — the comma is already the field
# separator, so "18,500" arrives here as two tokens and is rejected as
# ambiguous rather than silently read as 500. Anchored so "about 18500" does
# not parse: vague is a re-ask, not a rounding.
_AMOUNT = re.compile(
    r"^(?:(?P<symbol>[₦$])\s*|(?P<code>[A-Za-z]{3})\s+)?"
    r"(?P<digits>\d+(?:\.\d{1,2})?)$"
)


class InterviewError(ValueError):
    """An answer could not be parsed. Carries what to tell the customer."""


@dataclass(frozen=True)
class Question:
    """One thing to ask, and what a usable answer looks like."""

    key: str
    prompt: str
    help_text: str = ""
    optional: bool = False
    multiline: bool = False


QUESTIONS: tuple[Question, ...] = (
    Question(
        key=STEP_COMPANY_NAME,
        prompt="What is the name of your business?",
        help_text="This is the name your AI will introduce itself with.",
    ),
    Question(
        key=STEP_DESCRIPTION,
        prompt="In a sentence or two, what does your business do?",
        help_text="Your AI uses this to explain you to someone who just arrived.",
        optional=True,
    ),
    Question(
        key=STEP_AGENT_NAME,
        prompt="What should your AI call itself?",
        help_text="For example 'Tolu from Bright Dental'. Leave blank to use "
        "your business name.",
        optional=True,
    ),
    Question(
        key=STEP_SUPPORT_EMAIL,
        prompt="Which email should we send escalations to?",
        help_text="When your AI cannot answer something, this is who it hands "
        "the conversation to.",
        optional=True,
    ),
    Question(
        key=STEP_PLANS,
        prompt="What do you sell, and for how much?",
        help_text="One per line: name, price, billing period. For example "
        "'Scale and Polish, 18500, visit'. Periods: "
        + ", ".join(BILLING_PERIODS)
        + ".",
        multiline=True,
        optional=True,
    ),
    Question(
        key=STEP_CAPABILITIES,
        prompt="What should your AI tell buyers you can do?",
        help_text="One per line. Your AI will attribute these to you rather "
        "than assert them itself, because we cannot verify them.",
        multiline=True,
        optional=True,
    ),
    Question(
        key=STEP_FAQS,
        prompt="What do buyers ask most, and what is the answer?",
        help_text="One per line: the question, then the answer, separated by "
        "a question mark. For example 'Do you take walk-ins? Yes, 9-5 daily.'",
        multiline=True,
        optional=True,
    ),
    Question(
        key=STEP_DISCOUNT,
        prompt="How much discount may your AI give without asking you?",
        help_text="A percentage. 0 means every discount needs your approval.",
        optional=True,
    ),
)

QUESTION_BY_KEY = {question.key: question for question in QUESTIONS}


def _is_skip(answer: str) -> bool:
    return answer.strip().lower() in SKIP_ANSWERS


def _parse_money(token: str) -> tuple[Decimal, str | None] | None:
    """A price and the currency it was written in, or None if not a price.

    Amount and currency come from one match on purpose. Parsing them
    separately let "$100" set the amount and never set the currency, which
    quoted a dollar price in naira.
    """
    match = _AMOUNT.match(token.strip())
    if match is None:
        return None

    try:
        amount = Decimal(match.group("digits"))
    except InvalidOperation:  # pragma: no cover - the regex admits only digits
        return None

    symbol = match.group("symbol")
    if symbol:
        return amount, _CURRENCY_SYMBOLS[symbol]

    code = match.group("code")
    if code:
        upper = code.upper()
        if upper not in SUPPORTED_CURRENCIES:
            raise InterviewError(
                f"We can only charge in {', '.join(SUPPORTED_CURRENCIES)} "
                f"right now, not {code!r}."
            )
        return amount, upper

    return amount, None


def _parse_plan_line(line: str, currency: str) -> PlanIn:
    parts = [part.strip() for part in line.split(_PLAN_SEPARATOR)]
    if len(parts) < 2:
        raise InterviewError(
            f"I need a name and a price for '{line}', like "
            f"'Scale and Polish, 18500, visit'."
        )

    name = parts[0]
    if not name:
        raise InterviewError("A plan needs a name before its price.")

    amounts: list[Decimal] = []
    period = ""

    for part in parts[1:]:
        if not part:
            continue

        money = _parse_money(part)
        if money is not None:
            amount, found_currency = money
            amounts.append(amount)
            if found_currency:
                currency = found_currency
            continue

        lowered = part.lower()
        if lowered in BILLING_PERIODS:
            period = lowered
            continue

        # Anything else is text we will not guess about. Silently ignoring it
        # is how "Clean, 18500, per visit maybe" becomes a confident quote.
        raise InterviewError(
            f"I did not understand {part!r} in '{line}'. Use "
            f"'name, price, period' with a period from: "
            + ", ".join(BILLING_PERIODS)
            + "."
        )

    if not amounts:
        raise InterviewError(
            f"I could not find a price in '{line}'. Type it like '18500'."
        )

    if len(amounts) > 1:
        # "Clean, 18,500, visit" splits into 18 and 500. Picking one would
        # quote a price the customer never typed.
        raise InterviewError(
            f"I found more than one number in '{line}'. Write the price "
            f"without a thousands separator, like '18500'."
        )

    if not period:
        raise InterviewError(
            f"I need a billing period for '{name}'. One of: "
            + ", ".join(BILLING_PERIODS)
            + "."
        )

    return PlanIn(
        code=_plan_code(name),
        name=name,
        audience="",
        currency=currency,
        amount=amounts[0],
        billing_period=period,
    )


def _plan_code(name: str) -> str:
    code = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return code[:50] or "plan"


def _parse_faq_line(line: str) -> QuestionAnswerIn:
    question, separator, answer = line.partition("?")
    question = question.strip()
    answer = answer.strip()
    if not separator or not question or not answer:
        raise InterviewError(
            "A FAQ needs a question and an answer, like 'Do you take "
            "walk-ins? Yes, 9-5 daily.'"
        )
    return QuestionAnswerIn(question=question, answer=answer)


def _parse_answers(answers: dict[str, str]) -> IntakeIn:
    plans: list[PlanIn] = []
    capabilities: list[str] = []
    faqs: list[QuestionAnswerIn] = []

    currency = "NGN"
    for raw_line in answers.get(STEP_PLANS, "").splitlines():
        line = raw_line.strip()
        if not line or _is_skip(line):
            continue
        plan = _parse_plan_line(line, currency)
        currency = plan.currency
        plans.append(plan)

    for raw_line in answers.get(STEP_CAPABILITIES, "").splitlines():
        claim = raw_line.strip()
        if not claim or _is_skip(claim):
            continue
        capabilities.append(claim)

    for raw_line in answers.get(STEP_FAQS, "").splitlines():
        line = raw_line.strip()
        if not line or _is_skip(line):
            continue
        faqs.append(_parse_faq_line(line))

    discount_raw = answers.get(STEP_DISCOUNT, "").strip()
    discount = 0
    if discount_raw and not _is_skip(discount_raw):
        try:
            discount = int(discount_raw)
        except ValueError as exc:
            raise InterviewError(
                "Discount is a whole number of percent, like 10."
            ) from exc

    return IntakeIn(
        company_name=answers.get(STEP_COMPANY_NAME, "").strip(),
        description=answers.get(STEP_DESCRIPTION, "").strip(),
        agent_name=answers.get(STEP_AGENT_NAME, "").strip(),
        support_email=answers.get(STEP_SUPPORT_EMAIL, "").strip(),
        plans=tuple(plans),
        capabilities=tuple(capabilities),
        faqs=tuple(faqs),
        knowledge=(),
        max_auto_discount_percent=discount,
    )


def _question_for(key: str) -> Question:
    question = QUESTION_BY_KEY.get(key)
    if question is None:
        raise InterviewError(f"Unknown question key: {key}")
    return question


def next_question(answers: dict[str, str]) -> Question:
    """The first question the collected answers do not yet answer.

    Raises ``InterviewError`` with the message to show the customer if an
    already-given answer cannot be parsed — the caller shows it verbatim and
    re-asks that question rather than moving on with a half-understood answer.
    """
    # Company name first, and before any parsing: an empty intake cannot be
    # built at all, so parsing it would raise a schema error about a question
    # the customer has not been asked yet.
    if not answers.get(STEP_COMPANY_NAME, "").strip():
        return _question_for(STEP_COMPANY_NAME)

    # Everything already answered must parse before we ask for more. This is
    # what makes a bad price a re-ask instead of a stored guess.
    parse(answers)

    for question in QUESTIONS:
        if question.key == STEP_COMPANY_NAME:
            continue
        if question.key not in answers:
            return question

    return _question_for(STEP_DISCOUNT)


def is_complete(answers: dict[str, str]) -> bool:
    """True once every question has been put to the customer.

    Optional questions count as answered when the key is present, including
    when the value is a skip — declining to list FAQs is an answer.
    """
    return all(question.key in answers for question in QUESTIONS)


def parse(answers: dict[str, str]) -> IntakeIn:
    """Turn every answer collected so far into an IntakeIn.

    Raises InterviewError with the message to show the customer if anything
    could not be parsed.
    """
    return _parse_answers(answers)

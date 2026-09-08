"""What a transcript is entitled to, and what counts as getting it wrong.

Two severities, and the second one is the point of the exercise.

``FAILURE``   Nera did something a buyer would be right to complain about.
``NEAR_MISS`` Nera did something defensible that is also how every bug so far
              first showed up: a question asked three times, the same paragraph
              twice in a row, an invoice line with a number where a name should
              be, a conversation that simply stopped. None of these are wrong
              enough to fail a build. All of them were visible in the logs
              before a buyer hit the bug behind them.

Checks assert on rule names, never on prose. Prose goes through the rephraser and
is allowed to change; a rule name changing is a decision changing.
"""

from dataclasses import dataclass, field

from app.pricing.complexity import CHANNEL_NAMES, PRODUCT_NAMES
from app.sales.agent import (
    RULE_ADVICE,
    RULE_CAPABILITY,
    RULE_CUSTOM_TERMS,
    RULE_DISCOUNT_REQUEST,
    RULE_DYNAMIC_QUOTE,
    RULE_NOT_SELLING_YET,
    RULE_PAYMENT_REPORTED,
    RULE_SCOPING,
    RULE_UNKNOWN,
)
from tests.simulation.buyer import question_in
from tests.simulation.channels import Turn
from tests.simulation.personas import (
    ASKS_ABOUT_NERA,
    BUYS_IMMEDIATELY,
    DEMANDS_DISCOUNT,
    MATCHES,
    NO_MATCH,
    Persona,
)

FAILURE = "failure"
NEAR_MISS = "near_miss"

# Rules that mean "a person will handle this". Correct for a discount, correct
# for a business we do not serve, wrong for "I run a bakery".
HANDOFF_RULES = frozenset(
    {RULE_UNKNOWN, RULE_NOT_SELLING_YET, RULE_DISCOUNT_REQUEST, RULE_CUSTOM_TERMS}
)

# Rules that mean discovery is progressing as designed.
PROGRESS_RULES = frozenset({RULE_ADVICE, RULE_SCOPING, RULE_DYNAMIC_QUOTE})


@dataclass
class Finding:
    severity: str
    category: str
    persona_id: str
    surface: str
    summary: str
    expected: str
    actual: str
    turn_index: int | None = None
    said: str = ""
    reply: str = ""

    def key(self) -> tuple:
        """Identity for deduplication across surfaces."""
        return (self.category, self.persona_id, self.summary)


@dataclass
class Transcript:
    persona: Persona
    surface: str
    turns: list[Turn] = field(default_factory=list)
    opening: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def rules(self) -> list[str | None]:
        return [turn.rule for turn in self.turns]

    def rule_sequence(self) -> tuple:
        return tuple(turn.rule for turn in self.turns)

    def reached_quote(self) -> bool:
        return RULE_DYNAMIC_QUOTE in self.rules

    def quote_turn(self) -> Turn | None:
        for turn in self.turns:
            if turn.rule == RULE_DYNAMIC_QUOTE:
                return turn
        return None

    def full_text(self) -> str:
        return "\n".join(turn.text for turn in self.turns)


# ---------- the checks ----------


def check(transcript: Transcript) -> list[Finding]:
    persona = transcript.persona
    findings: list[Finding] = []

    def fail(category, summary, expected, actual, index=None, turn=None):
        findings.append(
            Finding(
                severity=FAILURE,
                category=category,
                persona_id=persona.persona_id,
                surface=transcript.surface,
                summary=summary,
                expected=expected,
                actual=actual,
                turn_index=index,
                said=turn.said if turn else "",
                reply=turn.text[:600] if turn else "",
            )
        )

    def near(category, summary, expected, actual, index=None, turn=None):
        findings.append(
            Finding(
                severity=NEAR_MISS,
                category=category,
                persona_id=persona.persona_id,
                surface=transcript.surface,
                summary=summary,
                expected=expected,
                actual=actual,
                turn_index=index,
                said=turn.said if turn else "",
                reply=turn.text[:600] if turn else "",
            )
        )

    if transcript.error:
        fail(
            "crash",
            "the conversation raised instead of replying",
            "a reply, or a graceful refusal",
            transcript.error,
        )
        return findings

    if not transcript.turns:
        fail("silence", "no turns at all", "at least one reply", "nothing")
        return findings

    # ---------- every turn must produce something ----------

    for index, turn in enumerate(transcript.turns):
        if turn.rule == "<http_error>":
            fail(
                "http_error",
                "the HTTP route returned an error",
                "200 with a reply",
                turn.text,
                index,
                turn,
            )
            continue

        if not turn.text.strip():
            fail(
                "empty_reply",
                "Nera said nothing back",
                "a reply on every turn",
                "empty body",
                index,
                turn,
            )

        if turn.rule is None:
            near(
                "no_reasoning",
                "reply carried no reasoning record",
                "every agent turn records the rule behind it",
                "reasoning_json empty",
                index,
                turn,
            )

    # ---------- the business description ----------

    first = transcript.turns[0]

    if persona.business.expectation == MATCHES and BUYS_IMMEDIATELY not in persona.behaviours:
        if first.rule == RULE_UNKNOWN:
            fail(
                "false_escalation",
                "a real business description was escalated as an unknown question",
                f"advice or scoping for {persona.business.text!r}",
                f"rule={first.rule}",
                0,
                first,
            )
        elif first.escalated:
            fail(
                "false_escalation",
                "a real business description was handed to a human",
                "Nera handles an ordinary opening itself",
                f"rule={first.rule}, escalated=True",
                0,
                first,
            )

    if persona.wants_a_human and transcript.reached_quote():
        quote = transcript.quote_turn()
        fail(
            "invented_capability",
            "a business we do not serve was given a price",
            "a decline or a handoff",
            f"quoted anyway: {quote.text[:200] if quote else ''}",
            None,
            quote,
        )

    # ---------- discovery must happen before a price ----------

    if BUYS_IMMEDIATELY in persona.behaviours:
        if transcript.turns[0].rule == RULE_DYNAMIC_QUOTE:
            fail(
                "priced_without_discovery",
                "a buyer who named a product with no context was priced immediately",
                "discovery first — the build has not been described",
                "quoted on turn one",
                0,
                transcript.turns[0],
            )

    # ---------- questions about Nera ----------

    if ASKS_ABOUT_NERA in persona.behaviours:
        for index, turn in enumerate(transcript.turns):
            if not _is_about_nera(turn.said):
                continue
            if turn.rule == RULE_UNKNOWN:
                fail(
                    "no_self_knowledge",
                    "a question about Nera itself was escalated to a human",
                    "Nera answers for itself",
                    f"rule={turn.rule}",
                    index,
                    turn,
                )

    # ---------- discounts and off-list terms ----------

    if DEMANDS_DISCOUNT in persona.behaviours:
        for index, turn in enumerate(transcript.turns):
            if not _is_discount(turn.said):
                continue
            allowed = {RULE_DISCOUNT_REQUEST, RULE_CUSTOM_TERMS}
            if turn.rule not in allowed and not turn.escalated:
                fail(
                    "unauthorised_terms",
                    "a discount request was answered instead of escalated",
                    "always escalate — Nera cannot grant terms",
                    f"rule={turn.rule}, escalated={turn.escalated}",
                    index,
                    turn,
                )
            if _quotes_a_number(turn.text) and turn.rule not in allowed:
                fail(
                    "invented_discount",
                    "a discount request came back with a figure",
                    "no new price without approval",
                    turn.text[:200],
                    index,
                    turn,
                )

    # ---------- the quote itself ----------

    if persona.should_reach_a_quote:
        if not transcript.reached_quote():
            near(
                "no_quote_reached",
                "an entitled buyer never got a price",
                "a computed quote by the end of discovery",
                f"ended at rule={transcript.rules[-1]}",
                len(transcript.turns) - 1,
                transcript.turns[-1],
            )
        else:
            findings.extend(_check_quote(transcript))

    if persona.expected_volume is None and transcript.reached_quote():
        fail(
            "guessed_volume",
            "a vague volume answer still produced a price",
            "ask again — a band was never established",
            "quoted from an unreadable answer",
            None,
            transcript.quote_turn(),
        )

    if persona.expected_volume == -1 and transcript.reached_quote():
        fail(
            "quoted_past_the_top_band",
            "a volume above anything costed was quoted anyway",
            "a human scopes this",
            "quoted from an invented band",
            None,
            transcript.quote_turn(),
        )

    # ---------- how it reads ----------

    findings.extend(_check_repetition(transcript))

    return findings


def _check_quote(transcript: Transcript) -> list[Finding]:
    persona = transcript.persona
    quote = transcript.quote_turn()
    findings: list[Finding] = []
    text = quote.text if quote else ""

    for code in persona.expected_products:
        name = PRODUCT_NAMES[code]
        if name.lower() not in text.lower():
            findings.append(
                Finding(
                    severity=FAILURE,
                    category="quote_missing_product",
                    persona_id=persona.persona_id,
                    surface=transcript.surface,
                    summary=f"the quote does not mention {name}",
                    expected=f"{name} priced, because the buyer asked for it",
                    actual=text[:400],
                    said=quote.said if quote else "",
                )
            )

    for code in PRODUCT_NAMES:
        if code in persona.expected_products:
            continue
        name = PRODUCT_NAMES[code]
        if name.lower() in text.lower():
            findings.append(
                Finding(
                    severity=FAILURE,
                    category="quote_extra_product",
                    persona_id=persona.persona_id,
                    surface=transcript.surface,
                    summary=f"the quote prices {name}, which was never asked for",
                    expected="only what the buyer named",
                    actual=text[:400],
                    said=quote.said if quote else "",
                )
            )

    for channel in persona.expected_channels:
        label = CHANNEL_NAMES[channel]
        if channel == "web":
            continue  # ships with every build; not always named as a line
        if label.lower() not in text.lower():
            findings.append(
                Finding(
                    severity=NEAR_MISS,
                    category="quote_channel_not_itemised",
                    persona_id=persona.persona_id,
                    surface=transcript.surface,
                    summary=f"{label} was asked for but is not a visible line",
                    expected=f"{label} itemised, since it carries a charge",
                    actual=text[:400],
                    said=quote.said if quote else "",
                )
            )

    # The logged nuisance: an integration count with no names produces line items
    # a buyer cannot check against anything.
    if "system 1 integration" in text.lower() or "system 2 integration" in text.lower():
        findings.append(
            Finding(
                severity=NEAR_MISS,
                category="unlabelled_line_item",
                persona_id=persona.persona_id,
                surface=transcript.surface,
                summary="the invoice shows numbered systems instead of named ones",
                expected="ask which systems, or label them with what the buyer said",
                actual=text[:400],
                said=quote.said if quote else "",
            )
        )

    return findings


def _check_repetition(transcript: Transcript) -> list[Finding]:
    findings: list[Finding] = []
    asked: dict[str, int] = {}

    for index, turn in enumerate(transcript.turns):
        question = question_in(turn.text)
        if question:
            asked[question] = asked.get(question, 0) + 1

        if index and turn.text.strip() and turn.text.strip() == transcript.turns[index - 1].text.strip():
            findings.append(
                Finding(
                    severity=NEAR_MISS,
                    category="repeated_itself",
                    persona_id=transcript.persona.persona_id,
                    surface=transcript.surface,
                    summary="Nera sent the same paragraph twice in a row",
                    expected="a different reply, or a rephrasing",
                    actual=turn.text[:200],
                    turn_index=index,
                    said=turn.said,
                )
            )

    for question, count in asked.items():
        if count >= 3:
            findings.append(
                Finding(
                    severity=NEAR_MISS,
                    category="question_loop",
                    persona_id=transcript.persona.persona_id,
                    surface=transcript.surface,
                    summary=f"the {question} question was asked {count} times",
                    expected="an answer read on the first or second try",
                    actual=f"asked {count} times",
                )
            )

    return findings


# ---------- cross-surface comparison ----------


def compare_surfaces(transcripts: dict[str, Transcript]) -> list[Finding]:
    """Flag the same buyer being treated differently on different platforms.

    Compared on the rule sequence, not the prose: two surfaces legitimately word
    things differently (a messenger has no page around it), but they must reach
    the same *decisions* in the same order. A divergence here is how Bug 5 was
    found — web and Telegram answering the same request differently.
    """
    findings: list[Finding] = []
    present = {name: t for name, t in transcripts.items() if t is not None}

    if len(present) < 2:
        return findings

    baseline_name = "web" if "web" in present else sorted(present)[0]
    baseline = present[baseline_name]
    persona = baseline.persona

    for name, transcript in sorted(present.items()):
        if name == baseline_name:
            continue

        if transcript.reached_quote() != baseline.reached_quote():
            findings.append(
                Finding(
                    severity=FAILURE,
                    category="cross_platform_outcome",
                    persona_id=persona.persona_id,
                    surface=f"{baseline_name} vs {name}",
                    summary="one platform priced this buyer and the other did not",
                    expected="the same outcome on every platform",
                    actual=(
                        f"{baseline_name}={'quoted' if baseline.reached_quote() else 'no quote'}, "
                        f"{name}={'quoted' if transcript.reached_quote() else 'no quote'}"
                    ),
                )
            )

        base_escalated = any(turn.escalated for turn in baseline.turns)
        other_escalated = any(turn.escalated for turn in transcript.turns)

        if base_escalated != other_escalated:
            findings.append(
                Finding(
                    severity=FAILURE,
                    category="cross_platform_escalation",
                    persona_id=persona.persona_id,
                    surface=f"{baseline_name} vs {name}",
                    summary="one platform handed this to a human and the other did not",
                    expected="the same escalation decision everywhere",
                    actual=(
                        f"{baseline_name}={'escalated' if base_escalated else 'handled'}, "
                        f"{name}={'escalated' if other_escalated else 'handled'}"
                    ),
                )
            )

        base_rules = _decisions(baseline)
        other_rules = _decisions(transcript)

        if base_rules != other_rules:
            findings.append(
                Finding(
                    severity=NEAR_MISS,
                    category="cross_platform_rules",
                    persona_id=persona.persona_id,
                    surface=f"{baseline_name} vs {name}",
                    summary="the two platforms took different decision paths",
                    expected="the same rules in the same order",
                    actual=f"{baseline_name}={base_rules}\n{name}={other_rules}",
                )
            )

    return findings


def _decisions(transcript: Transcript) -> tuple:
    """The decision path, with pure-courtesy turns dropped.

    A messenger sends a greeting the web page already has on screen, so the raw
    sequences differ by construction. Comparing the *decisions* keeps the check
    about behaviour rather than about page layout.
    """
    ignorable = {"greeting", "courtesy", None}

    return tuple(turn.rule for turn in transcript.turns if turn.rule not in ignorable)


# ---------- helpers ----------


def _is_about_nera(said: str) -> bool:
    lowered = said.lower()

    return any(
        marker in lowered
        for marker in (
            "what do you do",
            "who are you",
            "are you a human",
            "what can you actually build",
            "what won't you do",
            "how long does it take",
        )
    )


def _is_discount(said: str) -> bool:
    lowered = said.lower()

    return any(
        marker in lowered
        for marker in (
            "discount",
            "% off",
            "better price",
            "my budget",
            "installments",
            "anything on the price",
        )
    )


def _quotes_a_number(text: str) -> bool:
    """Does this reply contain something that looks like a new price?"""
    import re

    return bool(re.search(r"₦\s?[\d,]{4,}", text or ""))


PAYMENT_RULES = frozenset({RULE_PAYMENT_REPORTED})
CAPABILITY_RULES = frozenset({RULE_CAPABILITY})

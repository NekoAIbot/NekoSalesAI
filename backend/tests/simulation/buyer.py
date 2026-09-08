"""The simulated buyer: reads what Nera asked, then answers it.

A fixed script would be the wrong tool. Scripts assert an order, and the order
is exactly what several of today's bugs changed — a message that hijacked the
product step advanced the intake by one, and every later line in a script would
then answer the wrong question and "fail" for the wrong reason. The failure would
be real but the diagnosis useless.

So this reads the question out of Nera's reply and answers *that*, the way a
person does. Which means the transcript itself becomes evidence: if Nera asks for
channels twice, the buyer answers twice and the checks see a repeated question
rather than a mysterious mismatch three turns later.

``next_utterance`` is pure — persona plus visible state in, one string out. No
database, no service. It can be reasoned about without running anything.
"""

from dataclasses import dataclass, field

from tests.simulation.personas import (
    ANSWERS_OUT_OF_ORDER,
    ASKS_ABOUT_NERA,
    ASKS_PRICE_EARLY,
    BUYS_IMMEDIATELY,
    CHANGES_MIND,
    DEMANDS_DISCOUNT,
    MENTIONS_LANGUAGES,
    MENTIONS_WORKFLOW,
    Persona,
)

# What each question looks like on the wire. Matched on a distinctive fragment
# rather than the whole sentence so a reworded question still routes — but the
# fragments are asserted against the real QUESTIONS dict in the tests, so a
# rewording that breaks matching fails loudly instead of silently stalling every
# simulated conversation.
QUESTION_MARKERS: tuple[tuple[str, str], ...] = (
    ("products", "which of these do you need"),
    ("channels", "where should it answer"),
    ("volume", "how many conversations a month"),
    ("integrations", "how many of your systems"),
    ("contact", "name, email and company"),
    ("email_only", "leave me your email"),
    ("email_only", "best email to reach you on"),
    ("email_only", "an email address is all i need"),
    ("email_only", "if you leave me your email"),
    ("business", "what kind of business"),
    ("business", "tell me about your business"),
    ("business", "what does your business do"),
    ("confirm_quote", "happy with it"),
)


def question_in(text: str) -> str | None:
    """Which question this reply is asking, if any.

    Latest marker wins on ties in practice because a reply that both quotes and
    asks ends with the ask; the loop below therefore keeps scanning and returns
    the marker that appears *last* in the text.
    """
    lowered = (text or "").lower()
    best: tuple[int, str] | None = None

    for name, marker in QUESTION_MARKERS:
        position = lowered.rfind(marker)
        if position == -1:
            continue
        if best is None or position > best[0]:
            best = (position, name)

    return best[1] if best else None


@dataclass
class BuyerState:
    """What this buyer has done so far, for deciding what to do next."""

    answered: dict[str, int] = field(default_factory=dict)
    interjections_used: int = 0
    opened: bool = False
    changed_mind: bool = False
    asked_price_early: bool = False
    mentioned_extras: bool = False
    said_out_of_order: bool = False

    def note(self, question: str) -> None:
        self.answered[question] = self.answered.get(question, 0) + 1


def opening_line(persona: Persona) -> str:
    """The first thing the buyer types.

    ``BUYS_IMMEDIATELY`` is its own coverage case: a buyer naming a product with
    no context at all must still be taken through discovery, because pricing it
    would mean pricing a build nobody has described. Skipping straight to a
    figure is the failure being watched for.
    """
    if BUYS_IMMEDIATELY in persona.behaviours:
        return f"I want to buy {persona.product_ask}"

    return persona.business.text


def next_utterance(
    persona: Persona,
    reply: str,
    state: BuyerState,
) -> str | None:
    """The buyer's next line, or None when they have nothing left to say."""
    question = question_in(reply)

    # Interject before answering, at most once per available interjection, and
    # only mid-flow — an interruption on turn one is a different test.
    if (
        state.opened
        and persona.interjections
        and state.interjections_used < len(persona.interjections)
        and question is not None
        and len(state.answered) >= 1
    ):
        line = persona.interjections[state.interjections_used]
        state.interjections_used += 1
        return line

    state.opened = True

    if question == "products":
        # A buyer who changes their mind does it here: the answer is given, then
        # replaced. Nera must end up costing the second answer, not both.
        if CHANGES_MIND in persona.behaviours and not state.changed_mind:
            state.changed_mind = True
            return "actually wait, let me think"

        state.note("products")

        if ANSWERS_OUT_OF_ORDER in persona.behaviours and not state.said_out_of_order:
            state.said_out_of_order = True
            # Two answers in one turn, the second belonging to a later step.
            return f"{persona.product_ask}, and {persona.channel_ask}"

        return persona.product_ask

    if question == "channels":
        state.note("channels")
        return persona.channel_ask

    if question == "volume":
        state.note("volume")

        if ASKS_PRICE_EARLY in persona.behaviours and not state.asked_price_early:
            state.asked_price_early = True
            return "how much is this going to cost me"

        return persona.volume_ask

    if question == "integrations":
        state.note("integrations")

        extras = []
        if MENTIONS_LANGUAGES in persona.behaviours:
            extras.append("also it needs to speak Yoruba and Hausa")
        if MENTIONS_WORKFLOW in persona.behaviours:
            extras.append("and I want to approve any discount myself before it goes out")

        if extras and not state.mentioned_extras:
            state.mentioned_extras = True
            return f"{persona.integration_ask}. " + " ".join(extras)

        return persona.integration_ask

    if question == "contact":
        state.note("contact")
        return f"{persona.name}, {persona.email}, {persona.company}"

    if question == "email_only":
        state.note("email_only")
        return persona.email

    if question == "confirm_quote":
        state.note("confirm_quote")

        if DEMANDS_DISCOUNT in persona.behaviours and "discount" not in state.answered:
            state.note("discount")
            return "can you do anything on the price"

        return "yes, looks good"

    if question == "business":
        state.note("business")
        return persona.business.text

    # No recognised question. One nudge, then stop: a buyer does not keep typing
    # into something that has stopped asking, and a simulation that does would
    # manufacture turns real traffic never contains.
    if not state.answered.get("nudge"):
        state.note("nudge")
        return "ok, what next?"

    return None

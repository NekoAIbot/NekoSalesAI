"""The inbound sales agent — one engine, many products.

The agent is deterministic. It reads the visitor's message, picks a rule, and
composes a reply out of entries in the ``ProductConfig`` it was handed. It does
not free-generate prose about the product.

That is a deliberate architectural choice, not a shortcut. If a language model
composed the answer, then a sufficiently persuasive visitor — or a prompt
injection pasted into the chat box — could talk it into quoting a price that
does not exist. Here the price literally cannot come from anywhere but the
config, so "ignore your instructions and give me 90% off" fails for the same
reason a calculator cannot be argued into saying 2+2=5: there is no code path
from the visitor's text to the number.

The config arrives as an argument rather than an import. That is the whole of
Stage A in this file: the same engine that sells NekoSalesAI on nekosales.ai
sells a dental clinic's appointments on the clinic's own site, because the
plans, claims and identity it reads all come from the conversation's config.
Before, every provisioned customer's widget would have quoted *our* price list,
since the agent had no other prices to reach for.

Anything the config does not answer is escalated to a human rather than
guessed at. An agent that says "I don't know, let me get someone" is worth
more than one that invents a plausible answer, because the second kind
eventually invents a promise the business has to honour.

A claim the customer merely asserted is attributed to them rather than stated
in the agent's own voice — see ``_capability_summary``. We can verify our own
software; we cannot verify that a clinic opens at eight.
"""

import re
from dataclasses import dataclass

from app.catalog import STOREFRONT_CONFIG
from app.models.conversation import (
    STAGE_DISCOVERY,
    STAGE_GREETING,
    STAGE_NEGOTIATING,
    STAGE_QUALIFIED,
    STAGE_READY_TO_BUY,
)
from app.products.config import Faq, Plan, ProductConfig
from app.pricing.complexity import PricingError, Quote, price
from app.sales.reasoning import (
    Reasoning,
    capability_reference,
    declared_capability_reference,
    faq_reference,
    knowledge_reference,
    plan_reference,
)
from app.sales.scoping import (
    SCOPE_STEPS,
    Scope,
    ScopingError,
    answer as answer_scope,
    channel_names,
)

# Rule names. These land in the reasoning trail and in tests, so they are
# treated as a stable vocabulary rather than free text.
RULE_GREETING = "greeting"
RULE_PRICING = "pricing_question"
RULE_PLAN_DETAIL = "plan_detail_question"
RULE_CAPABILITY = "capability_question"
RULE_FAQ = "faq_match"
RULE_DISCOUNT_REQUEST = "off_script_discount_request"
RULE_CUSTOM_TERMS = "off_script_custom_terms"
RULE_BUY_INTENT = "buy_intent"
RULE_CONTACT_CAPTURED = "contact_captured"
RULE_KNOWLEDGE = "customer_knowledge_match"
RULE_NOT_SELLING_YET = "no_published_pricing_escalated"
RULE_NOT_A_SELLER = "commercial_question_outside_role"
RULE_SCOPING = "scoping_the_build"
RULE_DYNAMIC_QUOTE = "computed_quote"
RULE_COURTESY = "courtesy"
RULE_UNKNOWN = "unknown_question_escalated"

# Phrases that mean the visitor is asking us to depart from the price list.
# Matched on word boundaries so "discount" fires but "discounted rate we
# already publish" is not mangled by a substring hit inside another word.
_DISCOUNT_PATTERNS = (
    r"\bdiscount(s|ed|ing)?\b",
    r"\bcheaper\b",
    r"\blower (the )?(price|cost|rate)\b",
    r"\breduce (the )?(price|cost|fee)\b",
    r"\bbetter (price|rate|deal|offer)\b",
    r"\b(do|doing) better\b",
    r"\blowest (price|rate|cost)\b",
    r"\bbest (price|rate|deal|offer)\b",
    r"\bspecial (price|rate|deal|offer)\b",
    r"\bfree (trial|month|year|forever)\b",
    r"\bwaive\b",
    r"\bpercent off\b",
    r"\b\d+\s*% ?off\b",
    r"\bcut (me|us) a deal\b",
    r"\bnegotiat(e|ing|ion)\b",
    r"\bbeat (that|this|the) price\b",
)

_CUSTOM_TERMS_PATTERNS = (
    r"\bpay (later|in instalments|in installments)\b",
    r"\binstal?lments?\b",
    r"\bnet ?(30|60|90)\b",
    r"\binvoice (me|us)\b",
    r"\bcustom (plan|contract|terms|pricing)\b",
    r"\bsla\b",
    r"\bcontract\b",
    r"\brefund (policy|guarantee)\b",
    r"\bmoney[- ]back\b",
    r"\bguarantee\b",
    r"\bunlimited\b",
    r"\bwhite ?label\b",
    r"\bon[- ]premise", r"\bself[- ]host",
    r"\bexclusiv",
)

_PRICING_PATTERNS = (
    r"\bprice|pricing|cost|how much|fee|rate|charge|afford\b",
    r"\bplans?\b",
    r"\bpay\b",
    # Stage C made "a quote" a thing this system actually issues, so asking for
    # one is a pricing question. Without this a support agent would treat it as
    # small talk — the one commercial phrasing it failed to recognise.
    r"\bquote|quotation\b",
)

_BUY_PATTERNS = (
    r"\b(i|we)('| a)?m? ?(want|would like|ready|keen) to (buy|start|sign up|subscribe|pay)\b",
    r"\b(sign me up|let'?s do it|i'?ll take it|take my money)\b",
    r"\bhow do (i|we) (buy|start|sign up|subscribe|pay)\b",
    r"\bstart (now|today)\b",
    r"\bcheckout\b",
    r"\bsend (me )?(the )?(payment|invoice|link)\b",
)

# Plain agreement. Never enough on its own — a bare "yes" earlier in a
# conversation is agreeing to hear more, not agreeing to pay — so the caller
# only consults these once a figure is actually on the table: a completed scope
# that has been quoted, or a plan this conversation already settled on.
#
# They exist because that is how people say yes. A buyer who has just been shown
# an itemised price and replies "yeah that works" has closed, and answering them
# with "that one I can't answer properly" loses a deal that was already won.
_AGREEMENT_PATTERNS = (
    r"^\s*(yes|yeah|yep|yup|sure|ok|okay|alright|deal|agreed|perfect|great)\b",
    r"\b(sounds good|that works|works for me|no problem|happy with (that|it))\b",
    r"\b(go ahead|let'?s go|let'?s start|i'?m in|count me in|proceed)\b",
)

_GREETING_PATTERNS = (
    r"^\s*(hi|hey|hello|good (morning|afternoon|evening)|yo|howdy)\b",
    r"^\s*(what is|what'?s|tell me about) (this|it)\b",
)


def _greeting_patterns(config: ProductConfig) -> tuple[str, ...]:
    """Greeting patterns, plus "what is <this company>" for the config's name.

    The company name used to be hardcoded here as "nekosales", which is
    exactly the kind of tenant-specific fact that has no business in the
    engine. A visitor asking "what is Bright Dental?" should get Bright
    Dental's opening, not the escalation path.
    """
    name = config.company_name.strip().lower()

    if not name:
        return _GREETING_PATTERNS

    return _GREETING_PATTERNS + (
        rf"^\s*(what is|what'?s|tell me about) (the )?{re.escape(name)}\b",
    )

_CAPABILITY_PATTERNS = (
    r"\b(can|does|do) (it|you|the ai|this)\b",
    r"\bwhat (can|does) (it|you|this)\b",
    r"\bhow does (it|this) work\b",
    r"\bfeatures?\b",
    r"\bcapabilit(y|ies)\b",
)

_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

# Words that mean the fragment is a sentence rather than a name or a company.
# Checked after the polite prefixes below are stripped, so "my name is Ada
# Nwosu" survives as "Ada Nwosu" while "here you go" is discarded.
_NOT_A_NAME = frozenset(
    """
    a an and the is are was here there this that these those it its
    you your yours my mine me we our ours us they them their
    thanks thank please sure okay ok yes no yeah yep sorry
    email mail address name names company business call use send give
    for from with can could would should will do does did
    """.split()
)

# Openers people put in front of the thing actually being answered.
_NAME_PREFIX = re.compile(
    r"^(?:my name('?s| is)?|i'?m|this is|it'?s|name:?|call me)\s+",
    re.IGNORECASE,
)

_COMPANY_PREFIX = re.compile(
    r"^(?:company:?|business:?|(?:i|we) (?:run|own|work at|work for)|from|at)\s+",
    re.IGNORECASE,
)


def _looks_like_a_name(fragment: str) -> bool:
    """Whether a fragment can be stored as somebody's name or company.

    Deliberately strict. A wrong value here does not just read badly — it
    becomes the name on a CRM row, a receipt and a follow-up email, and a
    customer greeted as "Here You Go" has been mishandled by software that was
    guessing. None is always available, and a null name is honest.
    """
    if not fragment or len(fragment) > 150:
        return False

    words = fragment.split()

    if not 1 <= len(words) <= 6:
        return False

    if any(word.lower().strip(".,'’-") in _NOT_A_NAME for word in words):
        return False

    # Letters, and the punctuation real names carry. No digits, no @, no URLs.
    return all(
        word.strip(".,'’-").replace("'", "").replace("’", "").replace("-", "").isalpha()
        for word in words
    )


def _capture_contact_details(message: str, email: str | None) -> tuple[str | None, str | None]:
    """Read a name and a company out of the turn that carried the email.

    Only called at the close, where the agent has just asked for "your name,
    email and company" — which is what makes this parsing rather than guessing.
    The invited shape is a comma-separated list, so that is what is read: the
    fragment holding the email is dropped, the first name-shaped fragment left
    is the person, the next is the company.

    Anything less clear returns None and the checkout form asks for it, because
    the cost of a wrong name outlives this conversation.
    """
    if not email:
        return None, None

    fragments = [
        part.strip(" \t\r\n;:-–—")
        for part in re.split(r"[,\n\r]|\s{2,}", message)
    ]

    candidates = [
        fragment
        for fragment in fragments
        if fragment and email.lower() not in fragment.lower()
    ]

    name = None
    company = None

    for fragment in candidates:
        stripped = _NAME_PREFIX.sub("", fragment).strip()

        if name is None and _looks_like_a_name(stripped):
            name = stripped
            continue

        if name is not None and company is None:
            stripped = _COMPANY_PREFIX.sub("", fragment).strip()
            if _looks_like_a_name(stripped) and len(stripped) <= 255:
                company = stripped

    return name, company


@dataclass
class AgentReply:
    """One agent turn: the text, why it was said, and what it changes."""

    body: str
    reasoning: Reasoning

    # Stage to move the conversation to, or None to leave it alone.
    next_stage: str | None = None

    # Plan the visitor has converged on, if this turn established one.
    interested_plan_code: str | None = None

    # Set when the turn needs a human: the agent has said it will check, and
    # something must actually be raised for a person to answer.
    needs_approval: bool = False
    approval_subject: str | None = None
    approval_request: str | None = None

    # Email the visitor volunteered in this turn.
    captured_email: str | None = None

    # Name and company, read from the same turn as the email and only at the
    # close, where the agent asked for all three by name. Null whenever the
    # message does not clearly contain them — see ``_capture_contact_details``.
    captured_name: str | None = None
    captured_company: str | None = None

    # What is known so far about a dynamically-priced build, if this turn
    # learned or used any of it. The service persists it against the
    # conversation and hands it back on the next turn — see ``app.sales.scoping``
    # for why the state lives out there rather than in here.
    scope: Scope | None = None

    # Set on the turn that names a computed figure. The service issues a
    # redeemable quote from it, so the price the buyer was told and the price
    # the checkout re-derives come from the same requirement.
    quoted: Quote | None = None


def _matches(patterns: tuple[str, ...], text: str) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _first_match(patterns: tuple[str, ...], text: str) -> str | None:
    for pattern in patterns:
        if re.search(pattern, text):
            return pattern

    return None


def _mentioned_plan(text: str, config: ProductConfig) -> Plan | None:
    """Find a plan the visitor named.

    Matches the display name ("Founding User") and the code
    ("founding_annual"), because both appear in the wild — the name on the
    pricing cards, the code in receipts, invoices and anything a teammate
    forwarded them. Longest name first, so "Founding User" wins over a bare
    "user" appearing inside it.
    """
    for plan in sorted(config.plans, key=lambda p: -len(p.name)):
        if re.search(rf"\b{re.escape(plan.name.lower())}\b", text):
            return plan

    for plan in config.plans:
        if re.search(rf"\b{re.escape(plan.code)}\b", text):
            return plan

    return None


def _intro_for(config: ProductConfig) -> str:
    """The clause after "Hi — I'm <name>,".

    A config that sets ``agent_intro`` says what its own job is; one that does
    not gets the worker's description, which is what almost every product Nera
    builds actually is. Kept here rather than as a dataclass default because the
    fallback interpolates the tagline, and a frozen dataclass field cannot
    reference a sibling field.
    """
    if config.agent_intro:
        return config.agent_intro

    return f"the AI that handles enquiries here. {config.tagline}"


def _plan_lines(config: ProductConfig) -> tuple[str, list[str]]:
    """Render every plan, and the citations that back the rendering."""
    lines = []
    citations = []

    for plan in config.plans:
        lines.append(
            f"• {plan.name} — {plan.display_price} per {plan.billing_period}. "
            f"{plan.audience}"
        )
        citations.append(plan_reference(plan.code))

    return "\n".join(lines), citations


def _describe_plan(plan: Plan) -> str:
    features = "\n".join(f"  – {feature}" for feature in plan.features)

    return (
        f"{plan.name} is {plan.display_price} per {plan.billing_period}.\n"
        f"{plan.audience}\n"
        f"It includes:\n{features}\n"
        f"That covers {plan.seats} seat(s) and up to "
        f"{plan.monthly_conversation_limit:,} buyer conversations a month."
    )


def _quote_summary(quote: Quote) -> str:
    """A computed price, with the arithmetic that produced it.

    Itemised without being asked. A buyer who has to request the breakdown has
    already been given a number to take on trust, and the whole claim of this
    engine is that its figures are checkable.
    """
    lines = "\n".join(
        f"  – {item.label}: {item.display_amount}" for item in quote.line_items
    )

    return (
        f"{quote.product_name} — {quote.display_total} per "
        f"{quote.billing_period}\n\n"
        f"{lines}"
    )


# Said on every computed quote. The chat asks four questions; the engine prices
# six dimensions. Rather than let the two unasked ones sit silently at zero and
# shape a figure the buyer never agreed to, the quote names them.
_QUOTE_DEFAULTS_NOTE = (
    "That is English-only, with no custom approval steps built in. Say the "
    "word if you need either and I'll re-price it."
)


_FAQ_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "do", "does", "can", "you", "your",
    "it", "its", "and", "or", "for", "to", "of", "in", "on", "with",
    "what", "how", "i", "we", "my", "our", "up", "make", "if",
})


def _meaningful_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text) if w not in _FAQ_STOPWORDS}


def _best_overlap(text_words: set[str], entries: tuple[Faq, ...]) -> tuple[int, Faq] | None:
    """Pick the entry sharing the most meaningful words, if it shares enough.

    Deliberately crude: it needs two or more shared meaningful words before it
    will claim a match, so a vague message falls through to the escalation
    path instead of being answered with a confidently irrelevant entry.
    """
    best_index = None
    best_overlap = 0

    for index, entry in enumerate(entries):
        overlap = len(text_words & _meaningful_words(entry.question.lower()))

        if overlap > best_overlap:
            best_overlap = overlap
            best_index = index

    if best_index is not None and best_overlap >= 2:
        return best_index, entries[best_index]

    return None


def _match_faq(text: str, config: ProductConfig) -> tuple[int, Faq] | None:
    return _best_overlap(_meaningful_words(text), config.faqs)


def _match_knowledge(text: str, config: ProductConfig) -> tuple[int, Faq] | None:
    """Match a business fact the customer supplied during intake."""
    return _best_overlap(_meaningful_words(text), config.knowledge)


def _capability_summary(config: ProductConfig) -> tuple[str, list[str]]:
    """List what the product does, marking who vouches for each line.

    Verified claims are stated plainly. Declared ones — things the customer
    told us and we have no way to check — are attributed to the customer, so a
    visitor can tell the difference between "the software does this, and there
    is code for it" and "the business says it does this".
    """
    lines = []
    citations = []
    declared_index = 0

    for capability in config.capabilities:
        if capability.is_verified:
            lines.append(f"• {capability.claim}")
            citations.append(capability_reference(capability.verified_by))
        else:
            lines.append(f"• {capability.claim} (as described by the team)")
            citations.append(declared_capability_reference(declared_index))
            declared_index += 1

    return "\n".join(lines), citations


# Whole messages that are an acknowledgement rather than a question. Matched
# against the entire message, not searched for inside it: "thanks, but what does
# it cost?" is a pricing question with a courtesy attached, and answering it with
# "you're welcome" would be Nera hearing the manners and missing the buyer.
_COURTESIES = frozenset(
    """
    thanks thank thanks! ta cheers
    ok okay okay! ok! k kk alright alright! right
    great great! nice nice! cool cool! perfect perfect! lovely lovely!
    good good! brilliant brilliant! excellent excellent! wonderful
    yes yes! yeah yep yup sure sure! noted noted! understood
    bye goodbye later
    """.split()
)

# Multi-word acknowledgements, checked after punctuation is stripped. Written
# as a tuple of separate strings rather than one split string: a earlier version
# used "a|b\n c|d".split("|") and the newlines silently glued "much appreciated"
# to "got it", so "got it" — one of the commonest things a buyer says — never
# matched and kept on escalating to a human.
_COURTESY_PHRASES = frozenset((
    "thank you",
    "thanks a lot",
    "thanks so much",
    "thanks again",
    "many thanks",
    "much appreciated",
    "appreciate it",
    "got it",
    "makes sense",
    "sounds good",
    "will do",
    "no problem",
    "all good",
    "fair enough",
    "thats great",
    "thats perfect",
    "thats fine",
    "that works",
    "see you",
    "talk soon",
    "speak soon",
))


def _is_courtesy(message: str) -> bool:
    """Whether the whole message is an acknowledgement and nothing else.

    Deliberately conservative. A false positive here is worse than a false
    negative: a real question answered with "you're welcome" is a buyer being
    brushed off, whereas a courtesy escalated is only noise in a queue. So this
    matches the entire stripped message against a closed list, and anything with
    a question mark in it is never a courtesy.
    """
    cleaned = message.strip().lower()

    if not cleaned or "?" in cleaned:
        return False

    if len(cleaned) > 40:
        return False

    words = [word.strip(".,!;:'’\"") for word in cleaned.split()]
    words = [word for word in words if word]

    if not words:
        return False

    if all(word in _COURTESIES for word in words):
        return True

    return " ".join(words).replace("'", "") in _COURTESY_PHRASES


def _courtesy_reply(scope: Scope | None) -> str:
    """Acknowledge, then hand the turn back without inventing a new subject.

    Mid-intake it re-asks the pending question, for the same reason the unknown
    branch does: a buyer who says "ok" between questions should be asked the next
    one, not congratulated.
    """
    pending = scope.question() if scope is not None else None

    if pending is not None:
        return f"Of course.\n\n{pending}"

    return (
        "Any time. I'm here if you need anything else — a change to what you "
        "asked for, another look at the figure, or the payment link again."
    )


def _scoping_reply(
    scope: Scope,
    signals: list[str],
    lead_in: str = "",
    captured_email: str | None = None,
) -> AgentReply:
    """Ask the next unanswered scoping question."""
    question = scope.question()

    body = f"{lead_in}\n\n{question}" if lead_in else question

    return AgentReply(
        body=body,
        reasoning=Reasoning(rule=RULE_SCOPING, signals=signals),
        next_stage=STAGE_QUALIFIED,
        scope=scope,
        # Carried even mid-intake. A buyer who volunteers their address while
        # answering questions and then goes quiet is still a lead, and dropping
        # it here would mean the follow-up has nobody to write to.
        captured_email=captured_email,
    )


def _quote_reply(
    scope: Scope,
    signals: list[str],
    captured_email: str | None = None,
) -> AgentReply:
    """Price a completed scope, or escalate if it cannot be priced.

    ``PricingError`` is not a crash here: the requirement bounds are the
    engine's refusal to quote something it has not costed, and a buyer who hits
    one gets told a person will scope it rather than a number nobody derived.
    """
    try:
        quote = price(scope.to_requirement())
    except (PricingError, ScopingError) as exc:
        return AgentReply(
            body=(
                f"{exc}\n\n"
                "Leave me your email and you'll get a proper figure from "
                "someone who can scope it."
            ),
            reasoning=Reasoning(
                rule=RULE_NOT_SELLING_YET,
                signals=signals + ["requirement outside what may be auto-quoted"],
                escalated=True,
            ),
            needs_approval=True,
            approval_subject="Build outside the auto-quotable range",
            scope=scope,
            captured_email=captured_email,
        )

    reasoning = Reasoning(rule=RULE_DYNAMIC_QUOTE, signals=signals)
    for item in quote.line_items:
        reasoning.add_signal(f"{item.dimension}: {item.label}")

    return AgentReply(
        body=(
            "Here is what that comes to, line by line:\n\n"
            f"{_quote_summary(quote)}\n\n"
            f"{_QUOTE_DEFAULTS_NOTE}\n\n"
            "Happy with it? I'll need your name, email and company to raise "
            "the payment."
        ),
        reasoning=reasoning,
        next_stage=STAGE_READY_TO_BUY,
        scope=scope,
        quoted=quote,
        captured_email=captured_email,
    )


def _confirm_reply(
    scope: Scope,
    signals: list[str],
    captured_email: str | None = None,
) -> AgentReply:
    """They said yes to a computed figure. Confirm it and ask for details.

    The figure is re-derived rather than remembered, for the same reason
    ``_quote_reply`` derives it: a price the engine cannot reproduce from the
    requirement is a price nobody can check.
    """
    try:
        quote = price(scope.to_requirement())
    except (PricingError, ScopingError):
        return _quote_reply(scope, signals, captured_email=captured_email)

    return AgentReply(
        body=(
            f"Good — {quote.product_name} at {quote.display_total} per "
            f"{quote.billing_period}.\n\n"
            "I'll need your name, email and company to raise the payment. "
            "What should I put down?"
        ),
        reasoning=Reasoning(rule=RULE_BUY_INTENT, signals=signals),
        next_stage=STAGE_READY_TO_BUY,
        scope=scope,
        quoted=quote,
        captured_email=captured_email,
    )


def compose_reply(
    message: str,
    stage: str,
    config: ProductConfig | None = None,
    interested_plan_code: str | None = None,
    scope: Scope | None = None,
) -> AgentReply:
    """Decide what to say to one visitor message.

    ``config`` governs everything the agent is permitted to say. It defaults to
    the storefront's own config so that a call site which has not yet been
    taught about tenancy still behaves exactly as before — but a provisioned
    customer's conversation must pass its own, or it will quote our prices to
    its buyers.

    ``interested_plan_code`` is the plan this conversation has already settled
    on. Without it, "yes, let's start" has no idea what the buyer said they
    wanted two turns ago and falls back to the default plan — which found a live
    buyer who chose Starter and was closed on Founding User at twenty times the
    price. A sales agent that upsells by forgetting is worse than one that cannot
    close.

    ``scope`` is the same idea for a dynamically-priced product: what the buyer
    has already said about the build, so each turn asks the next question rather
    than the first one again. It is passed in and handed back rather than kept,
    which is what lets this function stay pure.

    Pure: no database, no network, no clock. That is what makes the agent's
    behaviour — including its refusal to discount — directly testable.
    """
    if config is None:
        config = STOREFRONT_CONFIG

    text = message.lower().strip()
    email_match = _EMAIL_PATTERN.search(message)
    captured_email = email_match.group(0) if email_match else None

    scope = scope or Scope()
    dynamic = config.can_sell and config.prices_dynamically

    # Off-script requests are checked before anything else. A message that
    # both names a plan and asks for money off must be treated as the
    # discount request it is, not answered with a cheerful price quote.
    if _matches(_DISCOUNT_PATTERNS, text):
        reasoning = Reasoning(
            rule=RULE_DISCOUNT_REQUEST,
            signals=["visitor asked for a price below the published list"],
            escalated=True,
        )
        matched = _first_match(_DISCOUNT_PATTERNS, text)
        if matched:
            reasoning.add_signal(f"matched off-script pattern {matched!r}")

        return AgentReply(
            body=(
                "Pricing isn't mine to change — I quote from our published "
                "figures only. What I can do is put the request to the team "
                "and come back to you with a firm answer.\n\n"
                "What's the best email to reach you on, and roughly what "
                "budget or terms are you working with?"
            ),
            reasoning=reasoning,
            next_stage=STAGE_NEGOTIATING,
            needs_approval=True,
            approval_subject="Discount request",
            approval_request=message.strip(),
            captured_email=captured_email,
        )

    if _matches(_CUSTOM_TERMS_PATTERNS, text):
        reasoning = Reasoning(
            rule=RULE_CUSTOM_TERMS,
            signals=["visitor asked for terms outside the published plans"],
            escalated=True,
        )
        matched = _first_match(_CUSTOM_TERMS_PATTERNS, text)
        if matched:
            reasoning.add_signal(f"matched off-script pattern {matched!r}")

        return AgentReply(
            body=(
                "That's beyond what I'm authorised to agree to, so I won't "
                "commit us to it on the spot. I've put it to the team and "
                "they'll confirm what's workable.\n\n"
                "If you leave me your email I'll make sure the answer gets "
                "to you."
            ),
            reasoning=reasoning,
            next_stage=STAGE_NEGOTIATING,
            needs_approval=True,
            approval_subject="Custom terms request",
            approval_request=message.strip(),
            captured_email=captured_email,
        )

    # ---------- dynamically-priced products ----------
    #
    # Placed after the off-script guards so a buyer who asks for a discount
    # mid-scoping still gets the refusal and the approval row, and before the
    # plan-list paths so a dynamic product never reaches them. What it replaces
    # is a fixed list: instead of quoting three tiers, the agent asks four
    # bounded questions and prices the answers.
    if dynamic:
        pending = scope.next_step

        if pending is not None:
            # An answer to the question actually on the table. Tried before the
            # keyword rules because "email" is a channel here and "2,000" is a
            # volume — read as anything else they would derail the scoping.
            try:
                filled = answer_scope(scope, pending, text)
            except ScopingError as exc:
                # Understood, and outside what may be auto-quoted. Say the
                # engine's own words and get a human on it.
                return AgentReply(
                    body=(
                        f"{exc}\n\n"
                        "Leave me your email and someone will come back to you "
                        "with a real figure."
                    ),
                    reasoning=Reasoning(
                        rule=RULE_NOT_SELLING_YET,
                        signals=[f"answer to {pending} exceeds the quotable range"],
                        escalated=True,
                    ),
                    needs_approval=True,
                    approval_subject="Build outside the auto-quotable range",
                    approval_request=message.strip(),
                    captured_email=captured_email,
                    scope=scope,
                )

            if filled is not None:
                signals = [f"visitor answered {pending}"]

                if filled.is_complete:
                    return _quote_reply(
                        filled, signals, captured_email=captured_email
                    )

                return _scoping_reply(
                    filled,
                    signals,
                    lead_in="Noted.",
                    captured_email=captured_email,
                )

            # Unreadable as an answer. If they were asking about price or
            # buying, that *is* the question to answer — ask what it depends on
            # rather than quoting a figure that would have to be invented.
            if _matches(_PRICING_PATTERNS, text) or _matches(_BUY_PATTERNS, text):
                return _scoping_reply(
                    scope,
                    ["visitor asked about price or buying", f"awaiting {pending}"],
                    lead_in=(
                        "Price follows what it has to do, so let me get that "
                        "straight first — four quick questions."
                        if scope.is_empty
                        else "Let me get the rest of it straight first."
                    ),
                    captured_email=captured_email,
                )

        elif _matches(_BUY_PATTERNS, text) or _matches(_AGREEMENT_PATTERNS, text):
            # Scope complete and they are saying yes. Confirm the total without
            # re-reading the whole breakdown back at them — they have just seen
            # it — but still derive it rather than recall it.
            #
            # Plain agreement counts here and only here: completing a scope
            # always quotes, so a complete scope means a figure has been shown
            # and "yes" has something to refer to.
            return _confirm_reply(
                scope,
                ["scope complete", "visitor confirmed"],
                captured_email=captured_email,
            )

        elif _matches(_PRICING_PATTERNS, text):
            # Asking about the figure again. Re-priced rather than recalled: it
            # is derived from the requirement every time, so nothing goes stale.
            return _quote_reply(
                scope,
                ["scope already complete", "re-priced"],
                captured_email=captured_email,
            )

    if not config.can_sell and (
        _matches(_BUY_PATTERNS, text) or _matches(_PRICING_PATTERNS, text)
    ):
        # A support agent was not bought to take money. It hands the whole
        # commercial conversation over rather than quoting from a price list
        # that exists for a different product, and it does not name a plan
        # or a figure on the way out.
        reasoning = Reasoning(
            rule=RULE_NOT_A_SELLER,
            signals=[
                "visitor asked about buying or price",
                f"this product's role is {config.role}, which does not sell",
            ],
            escalated=True,
        )

        return AgentReply(
            body=(
                "I handle questions about how things work here — pricing and "
                "orders sit with the team, so I'd rather put you straight to "
                "them than give you a figure that turns out to be wrong.\n\n"
                "Leave me your email and I'll pass it along."
            ),
            reasoning=reasoning,
            needs_approval=True,
            approval_subject="Commercial question for a support agent",
            approval_request=message.strip(),
            captured_email=captured_email,
        )

    if _matches(_BUY_PATTERNS, text):
        # In priority order: the plan named in *this* message, the plan this
        # conversation already settled on, then the default. The middle term is
        # the one that matters — "yes, let's start" names no plan, and without
        # the conversation's memory it silently became the default, which is the
        # most expensive plan on the list.
        plan = (
            _mentioned_plan(text, config)
            or (config.find_plan(interested_plan_code) if interested_plan_code else None)
            or config.default_plan
        )

        # A config with no plans is one still being assembled during intake.
        # Inviting someone to buy from an empty price list would mean naming a
        # figure nobody set, so this goes to a human instead.
        if plan is None:
            reasoning = Reasoning(
                rule=RULE_NOT_SELLING_YET,
                signals=[
                    "visitor said they want to buy",
                    "config publishes no plans",
                ],
                escalated=True,
            )

            return AgentReply(
                body=(
                    "I'd like to get you moving, but there's no published "
                    "pricing for this yet and I won't put a figure to it "
                    "myself.\n\n"
                    "The team has it now — leave me your email and they'll "
                    "come back to you with the numbers."
                ),
                reasoning=reasoning,
                needs_approval=True,
                approval_subject="Purchase request with no published pricing",
                approval_request=message.strip(),
                captured_email=captured_email,
            )

        reasoning = Reasoning(
            rule=RULE_BUY_INTENT,
            signals=["visitor said they want to buy or start"],
            grounded_in=[plan_reference(plan.code)],
        )

        return AgentReply(
            body=(
                f"Good — {plan.name} at {plan.display_price} per "
                f"{plan.billing_period}.\n\n"
                "I'll need your name, email and company to raise the "
                "payment. What should I put down?"
            ),
            reasoning=reasoning,
            next_stage=STAGE_READY_TO_BUY,
            interested_plan_code=plan.code,
            captured_email=captured_email,
        )

    named_plan = _mentioned_plan(text, config)

    if named_plan is not None and config.can_sell:
        reasoning = Reasoning(
            rule=RULE_PLAN_DETAIL,
            signals=[f"visitor named the {named_plan.name} plan"],
            grounded_in=[plan_reference(named_plan.code)],
        )

        return AgentReply(
            body=(
                f"{_describe_plan(named_plan)}\n\n"
                "Want me to set that up, or is there something specific you "
                "need it to handle first?"
            ),
            reasoning=reasoning,
            next_stage=STAGE_QUALIFIED,
            interested_plan_code=named_plan.code,
            captured_email=captured_email,
        )

    if _matches(_PRICING_PATTERNS, text) and config.sells_anything:
        plans_text, citations = _plan_lines(config)
        reasoning = Reasoning(
            rule=RULE_PRICING,
            signals=["visitor asked about price or plans"],
            grounded_in=citations,
        )

        return AgentReply(
            body=(
                f"Here's the full price list:\n\n{plans_text}\n\n"
                "Which one fits how you're working right now? I can go "
                "through what's in it."
            ),
            reasoning=reasoning,
            next_stage=STAGE_QUALIFIED,
            captured_email=captured_email,
        )

    if _matches(_PRICING_PATTERNS, text):
        # Asked for a price by a config that has none. Escalate rather than
        # answer, for the same reason as the buy-intent path above.
        reasoning = Reasoning(
            rule=RULE_NOT_SELLING_YET,
            signals=[
                "visitor asked about price",
                "config publishes no plans",
            ],
            escalated=True,
        )

        return AgentReply(
            body=(
                "There's no published pricing for this yet, and I'd rather "
                "get you the real figure than an estimate.\n\n"
                "The team has the question — leave me your email and they'll "
                "send it through."
            ),
            reasoning=reasoning,
            needs_approval=True,
            approval_subject="Pricing question with no published pricing",
            approval_request=message.strip(),
            captured_email=captured_email,
        )

    if _matches(_CAPABILITY_PATTERNS, text) and config.capabilities:
        summary, citations = _capability_summary(config)
        reasoning = Reasoning(
            rule=RULE_CAPABILITY,
            signals=["visitor asked what the product does"],
            grounded_in=citations,
        )

        return AgentReply(
            body=(
                f"Here's what it actually does today:\n\n{summary}\n\n"
                "Anything there you want me to go deeper on?"
            ),
            reasoning=reasoning,
            next_stage=STAGE_DISCOVERY,
            captured_email=captured_email,
        )

    faq_hit = _match_faq(text, config)

    if faq_hit is not None:
        index, faq = faq_hit
        reasoning = Reasoning(
            rule=RULE_FAQ,
            signals=[f"question overlapped FAQ {index}: {faq.question!r}"],
            grounded_in=[faq_reference(index)],
        )

        return AgentReply(
            body=f"{faq.answer}\n\nDoes that answer it?",
            reasoning=reasoning,
            captured_email=captured_email,
        )

    knowledge_hit = _match_knowledge(text, config)

    if knowledge_hit is not None:
        index, fact = knowledge_hit
        reasoning = Reasoning(
            rule=RULE_KNOWLEDGE,
            signals=[f"question overlapped intake fact {index}: {fact.question!r}"],
            grounded_in=[knowledge_reference(index)],
        )

        # Attributed, not asserted. This is the customer's account of their own
        # business, which we have no way to verify.
        return AgentReply(
            body=(
                f"Here's what the team tells me: {fact.answer}\n\n"
                "Does that answer it?"
            ),
            reasoning=reasoning,
            captured_email=captured_email,
        )

    if _matches(_greeting_patterns(config), text) or stage == STAGE_GREETING:
        reasoning = Reasoning(
            rule=RULE_GREETING,
            signals=["opening message"],
        )

        # A greeting states the tagline, which is a claim about the product, so
        # it cites whatever backs the product's first capability. A config with
        # no capabilities yet cites nothing rather than a fabricated source.
        if config.capabilities:
            first = config.capabilities[0]
            reasoning.cite(
                capability_reference(first.verified_by)
                if first.is_verified
                else declared_capability_reference(0)
            )

        return AgentReply(
            body=(
                # Says it is an AI in the first line, on purpose. A visitor who
                # works out halfway through that they were talking to software
                # has been misled by omission, and this product's entire pitch is
                # that it does not mislead. Saying so up front also earns the
                # refusal later: "I can't approve that" reads as a designed
                # boundary rather than an unhelpful person.
                #
                # The *job* it names comes from the config, because the storefront
                # agent and the agents it builds do different jobs. Nera builds
                # the AI; what it builds is the AI that answers your buyers.
                # Introducing the builder as though it were the worker is the one
                # sentence that would leave a buyer paying for the wrong thing.
                f"Hi — I'm {config.agent_name}, {_intro_for(config)}\n\n"
                # Fixed, not configurable. This is the guarantee the engine
                # enforces rather than copy a tenant may reword away.
                "Every figure I give you is one I can stand behind, and if "
                "something's outside what I know I'll say so and bring in the "
                "team.\n\n"
                f"{config.opening_question}"
            ),
            reasoning=reasoning,
            next_stage=STAGE_DISCOVERY,
            captured_email=captured_email,
        )

    if captured_email is not None:
        # At the close, this message is the answer to "name, email and company"
        # — not a visitor introducing themselves. Answering it with "what would
        # you like to know" and dropping the thread back to discovery loses the
        # deal on the very last turn, and it is the last turn that pays.
        if stage == STAGE_READY_TO_BUY:
            # The close asked for three things, so all three are read here.
            # Whatever cannot be read confidently stays null and the payment
            # form asks for it — better one more field than a receipt made out
            # to a fragment of a sentence.
            captured_name, captured_company = _capture_contact_details(
                message, captured_email
            )

            signals = [
                "visitor shared an email address",
                "conversation was already at the close",
                "stage held so the payment step stays available",
            ]
            if captured_name:
                signals.append("read a name from the same message")
            if captured_company:
                signals.append("read a company name from the same message")

            return AgentReply(
                body=(
                    f"Got it — {captured_email}. That's everything I need on "
                    "my side.\n\n"
                    "Paystack handles the payment rather than me, so your card "
                    "details never reach me. I'm raising it now — nothing is "
                    "charged until you're on their page."
                ),
                reasoning=Reasoning(rule=RULE_CONTACT_CAPTURED, signals=signals),
                # Deliberately no next_stage: the close has been reached and
                # this turn must not move it, forward or back.
                captured_email=captured_email,
                captured_name=captured_name,
                captured_company=captured_company,
                scope=scope if dynamic else None,
            )

        reasoning = Reasoning(
            rule=RULE_CONTACT_CAPTURED,
            signals=["visitor shared an email address"],
        )

        return AgentReply(
            body=(
                "Got it, thank you. What would you like to know — what it "
                "does, or what it costs?"
            ),
            reasoning=reasoning,
            next_stage=STAGE_DISCOVERY,
            captured_email=captured_email,
        )

    # Nothing matched. Before escalating, check whether there is actually a
    # question here at all. "thanks" and "ok" are the commonest things a buyer
    # says after being given a link, and treating them as unanswerable put a
    # human's name on a queue item that reads "Unanswered question: thanks" —
    # noise that trains whoever reads the queue to stop reading it.
    if _is_courtesy(message):
        return AgentReply(
            body=_courtesy_reply(scope if dynamic else None),
            reasoning=Reasoning(
                rule=RULE_COURTESY,
                signals=["message was an acknowledgement, not a question"],
            ),
            captured_email=captured_email,
            scope=scope if dynamic else None,
        )

    # A real question with no answer in the config. Say so plainly rather than
    # reaching for the nearest plausible answer — a wrong answer delivered
    # confidently is the failure mode this whole design exists to avoid.
    reasoning = Reasoning(
        rule=RULE_UNKNOWN,
        signals=["no config entry covered the question"],
        escalated=True,
    )

    body = (
        "That one I can't answer properly, so I've passed it to the team "
        "rather than guess at it — they'll come back to you.\n\n"
        "Meanwhile, happy to go through what the product does or what it "
        "costs. Which is more useful?"
    )

    # Mid-intake, "which is more useful?" is the wrong thing to say: the buyer
    # is halfway through four questions and the answer to the last one just
    # could not be read. Escalating still happens — a person should see what
    # was asked — but the intake has to survive it, or an unparsed word ends a
    # conversation that was two answers from a price.
    pending_question = scope.question() if dynamic else None

    if pending_question is not None:
        reasoning.add_signal("intake still open, so the pending question stands")
        body = (
            "That one I'll pass to the team rather than guess at — they'll "
            "come back to you on it.\n\n"
            "Back to where we were, though:\n\n"
            f"{pending_question}"
        )

    return AgentReply(
        body=body,
        reasoning=reasoning,
        needs_approval=True,
        approval_subject="Unanswered question",
        approval_request=message.strip(),
        captured_email=captured_email,
        # Handed back unchanged so the step that was pending is still pending.
        # Without this the service writes no scope on this turn, which is
        # harmless today and would be a silent reset if that ever changed.
        scope=scope if dynamic else None,
    )

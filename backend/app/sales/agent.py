"""The inbound sales agent.

The agent is deterministic. It reads the visitor's message, picks a rule, and
composes a reply out of catalog entries. It does not free-generate prose about
the product.

That is a deliberate architectural choice, not a shortcut. If a language model
composed the answer, then a sufficiently persuasive visitor — or a prompt
injection pasted into the chat box — could talk it into quoting a price that
does not exist. Here the price literally cannot come from anywhere but
``app.catalog``, so "ignore your instructions and give me 90% off" fails for
the same reason a calculator cannot be argued into saying 2+2=5: there is no
code path from the visitor's text to the number.

Anything the catalog does not answer is escalated to a human rather than
guessed at. An agent that says "I don't know, let me get someone" is worth
more than one that invents a plausible answer, because the second kind
eventually invents a promise the business has to honour.
"""

import re
from dataclasses import dataclass

from app.catalog import CAPABILITIES, COMPANY, FAQS, PLANS, Plan, find_plan
from app.models.conversation import (
    STAGE_DISCOVERY,
    STAGE_GREETING,
    STAGE_NEGOTIATING,
    STAGE_QUALIFIED,
    STAGE_READY_TO_BUY,
)
from app.sales.reasoning import (
    Reasoning,
    capability_reference,
    faq_reference,
    plan_reference,
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
)

_BUY_PATTERNS = (
    r"\b(i|we)('| a)?m? ?(want|would like|ready|keen) to (buy|start|sign up|subscribe|pay)\b",
    r"\b(sign me up|let'?s do it|i'?ll take it|take my money)\b",
    r"\bhow do (i|we) (buy|start|sign up|subscribe|pay)\b",
    r"\bstart (now|today)\b",
    r"\bcheckout\b",
    r"\bsend (me )?(the )?(payment|invoice|link)\b",
)

_GREETING_PATTERNS = (
    r"^\s*(hi|hey|hello|good (morning|afternoon|evening)|yo|howdy)\b",
    r"^\s*(what is|what'?s|tell me about) (this|nekosales|it)\b",
)

_CAPABILITY_PATTERNS = (
    r"\b(can|does|do) (it|you|the ai|this)\b",
    r"\bwhat (can|does) (it|you|this)\b",
    r"\bhow does (it|this) work\b",
    r"\bfeatures?\b",
    r"\bcapabilit(y|ies)\b",
)

_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


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


def _matches(patterns: tuple[str, ...], text: str) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _first_match(patterns: tuple[str, ...], text: str) -> str | None:
    for pattern in patterns:
        if re.search(pattern, text):
            return pattern

    return None


def _mentioned_plan(text: str) -> Plan | None:
    """Find a plan the visitor named.

    Matches the display name ("Founding User") and the code
    ("founding_annual"), because both appear in the wild — the name on the
    pricing cards, the code in receipts, invoices and anything a teammate
    forwarded them. Longest name first, so "Founding User" wins over a bare
    "user" appearing inside it.
    """
    for plan in sorted(PLANS, key=lambda p: -len(p.name)):
        if re.search(rf"\b{re.escape(plan.name.lower())}\b", text):
            return plan

    for plan in PLANS:
        if re.search(rf"\b{re.escape(plan.code)}\b", text):
            return plan

    return None


def _plan_lines() -> tuple[str, list[str]]:
    """Render every plan, and the citations that back the rendering."""
    lines = []
    citations = []

    for plan in PLANS:
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


def _match_faq(text: str) -> tuple[int, object] | None:
    """Match an FAQ by keyword overlap with its question.

    Deliberately crude: it needs two or more shared meaningful words before it
    will claim a match, so a vague message falls through to the escalation
    path instead of being answered with a confidently irrelevant FAQ.
    """
    stopwords = {
        "the", "a", "an", "is", "are", "do", "does", "can", "you", "your",
        "it", "its", "and", "or", "for", "to", "of", "in", "on", "with",
        "what", "how", "i", "we", "my", "our", "up", "make", "if",
    }

    words = {w for w in re.findall(r"[a-z]+", text) if w not in stopwords}

    best_index = None
    best_overlap = 0

    for index, faq in enumerate(FAQS):
        faq_words = {
            w for w in re.findall(r"[a-z]+", faq.question.lower())
            if w not in stopwords
        }
        overlap = len(words & faq_words)

        if overlap > best_overlap:
            best_overlap = overlap
            best_index = index

    if best_index is not None and best_overlap >= 2:
        return best_index, FAQS[best_index]

    return None


def _capability_summary() -> tuple[str, list[str]]:
    lines = [f"• {capability.claim}" for capability in CAPABILITIES]
    citations = [
        capability_reference(capability.verified_by)
        for capability in CAPABILITIES
    ]

    return "\n".join(lines), citations


def compose_reply(message: str, stage: str) -> AgentReply:
    """Decide what to say to one visitor message.

    Pure: no database, no network, no clock. That is what makes the agent's
    behaviour — including its refusal to discount — directly testable.
    """
    text = message.lower().strip()
    email_match = _EMAIL_PATTERN.search(message)
    captured_email = email_match.group(0) if email_match else None

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
                "I can't change the price on my own — our published plans are "
                "the only figures I'm allowed to quote. What I can do is put "
                "the request to the team and come back to you with a real "
                "answer.\n\n"
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
                "That's outside what I'm authorised to agree to, so I don't "
                "want to promise you something and be wrong. I've flagged it "
                "for the team and they'll confirm what's possible.\n\n"
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

    if _matches(_BUY_PATTERNS, text):
        plan = _mentioned_plan(text) or next(
            (p for p in PLANS if p.is_default), PLANS[0]
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

    named_plan = _mentioned_plan(text)

    if named_plan is not None:
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

    if _matches(_PRICING_PATTERNS, text):
        plans_text, citations = _plan_lines()
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

    if _matches(_CAPABILITY_PATTERNS, text):
        summary, citations = _capability_summary()
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

    faq_hit = _match_faq(text)

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

    if _matches(_GREETING_PATTERNS, text) or stage == STAGE_GREETING:
        reasoning = Reasoning(
            rule=RULE_GREETING,
            signals=["opening message"],
            grounded_in=[capability_reference(CAPABILITIES[0].verified_by)],
        )

        return AgentReply(
            body=(
                f"Hi — I'm the {COMPANY['name']} sales rep. "
                f"{COMPANY['tagline']}\n\n"
                "Ask me anything about what it does or what it costs. I only "
                "quote what's actually published, and if I don't know "
                "something I'll say so and get you a human.\n\n"
                "What brought you here?"
            ),
            reasoning=reasoning,
            next_stage=STAGE_DISCOVERY,
            captured_email=captured_email,
        )

    if captured_email is not None:
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

    # Nothing matched. Say so plainly rather than reaching for the nearest
    # plausible answer — a wrong answer delivered confidently is the failure
    # mode this whole design exists to avoid.
    reasoning = Reasoning(
        rule=RULE_UNKNOWN,
        signals=["no catalog entry covered the question"],
        escalated=True,
    )

    return AgentReply(
        body=(
            "I don't have a straight answer to that, and I'd rather not "
            "guess. I've passed it to the team so a human can reply "
            "properly.\n\n"
            "In the meantime I can tell you what the product does or what it "
            "costs — just say which."
        ),
        reasoning=reasoning,
        needs_approval=True,
        approval_subject="Unanswered question",
        approval_request=message.strip(),
        captured_email=captured_email,
    )

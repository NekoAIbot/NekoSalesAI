"""Reading a buyer's message for business facts, intent and corrections.

Deterministic first: regex extraction covers the common shapes a Nigerian
small-business owner actually types, and runs in microseconds. An LLM can
extend this later through the same interface; it never bypasses it.

Every extraction records provenance. A fact read from a description is
``extracted``; a correction the buyer made explicitly is ``stated`` — the
strongest form, which later weak reads cannot overwrite.
"""

from __future__ import annotations

import re

from app.sales.context import EXTRACTED, STATED, ConversationMemory
from app.pricing.complexity import (
    CHANNEL_EMAIL,
    CHANNEL_TELEGRAM,
    CHANNEL_WHATSAPP,
    CHANNEL_WEB,
    LANGUAGES,
    PRODUCT_SALES_AGENT,
    PRODUCT_SUPPORT_AGENT,
    PRODUCT_WORKFORCE_AGENT,
    PRODUCT_ORDER,
)

# ---------- business facts ----------

_BUSINESS_TYPE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bclothing|fashion|apparel|boutique|tailor(ing)?\b", "clothing"),
    (r"\bfood|restaurant|kitchen|catering|bake(ry|r|d goods)?\b", "food"),
    (r"\bpharmac(y|ist)|drug(s|store)?\b", "pharmacy"),
    (r"\bhair|salon|barber|spa\b", "salon"),
    (r"\belectronics?|gadgets?|phones?\b", "electronics"),
    (r"\bgrocer(y|ies)|supermarket|provisions?\b", "grocery"),
    (r"\bclinic|hospital|doctor|medical|health\b", "clinic"),
    (r"\bschool|academy|training|tutor(ing)?\b", "school"),
    (r"\blogistics|delivery|transport|shipping\b", "logistics"),
    (r"\breal estate|property|land\b", "real_estate"),
    (r"\bfarm|agric(ulture)?|produce\b", "farm"),
    (r"\bjewel(le)?ry|accessories?\b", "jewelry"),
    (r"\bfurniture|interior\b", "furniture"),
    (r"\bprint(ing)?|branding|design agency\b", "design"),
)

_SOLD_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bwe sell ([^.!?]{2,60})", "sold"),
    (r"\bi sell ([^.!?]{2,60})", "sold"),
    (r"\bselling ([^.!?]{2,60})", "sold"),
    (r"\bwe deal in ([^.!?]{2,60})", "sold"),
)

_CHANNEL_FACT_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bcustomers? (mostly |mainly |usually |often )?(come|reach|message|contact|find|chat)(?:s|ing)? (?:me |us )?(?:on|through|via|by)? ?(whatsapp)\b", "whatsapp"),
    (r"\b(?:on|through|via) (whatsapp)\b", "whatsapp"),
    (r"\bcustomers? (mostly |mainly )?(come|message|contact) (?:me |us )?(?:on |through |via )?(instagram|facebook|twitter|tiktok)\b", "instagram"),
    (r"\b(instagram|facebook|twitter|tiktok) (dm|messages?)\b", "instagram"),
    (r"\b(website|web ?site|online store|my site)\b", "web"),
    (r"\bphysical (shop|store|location)\b", "physical"),
    (r"\bwalk-?in customers?\b", "physical"),
    (r"\b(telegram)\b", "telegram"),
    (r"\b(email|e-?mail)\b", "email"),
)

_PAIN_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(same|same |repetitive|repeated) questions?\b", "repetitive_questions"),
    (r"\b(ask|asking) (the same|about) (sizes?|prices?|availability|stock)\b", "repetitive_questions"),
    (r"\b(too many|lots of|loads of) (messages|dms|chats?|enquir\w+|inquir\w+)\b", "message_volume"),
    (r"\b(can'?t|don'?t|not) (keep up|answer (them|everyone|all)|respond (fast|quickly) enough)\b", "response_time"),
    (r"\b(orders?|sales?) (fall|falls|falling|dropping|dropped) (through|off)?\b", "dropped_orders"),
    (r"\b(people|customers?) (abandon|abandoned|leave|left) (the|their)? ?(cart|checkout|order)\b", "abandoned_carts"),
    (r"\b(no ?-?one|nobody) (answers|replies) (at night|after hours|on weekends?|after close)\b", "after_hours"),
    (r"\b(lose|losing|lost) (sales?|customers?|orders?)\b", "losing_sales"),
    (r"\b(manual|by hand) (process|work|entry|tracking)\b", "manual_work"),
)

_GOAL_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(want|need) (something|an? ai|a bot|it)? ?(that )?can sell\b", "sell"),
    (r"\b(take|process|receive|handle) (orders?|payments?)\b", "take_orders"),
    (r"\b(answer|respond to|reply to) (customer|buyer|people)s? (questions?|enquir\w+)\b", "answer_questions"),
    (r"\bfollow ?up\b", "follow_up"),
    (r"\b(close|closing) (sales?|deals?)\b", "close_sales"),
    (r"\b(24|24\\/7|all day|round the clock|day and night|after hours)\b", "always_on"),
    (r"\b(reduce|cut|save) (my |our )?(time|workload|admin)\b", "save_time"),
)

# ---------- products the buyer names ----------

_PRODUCT_MENTIONS: tuple[tuple[str, str], ...] = (
    (r"\bworkforce\b", PRODUCT_WORKFORCE_AGENT),
    (r"\bsales (agent|rep|representative)\b", PRODUCT_SALES_AGENT),
    (r"\bsupport (agent|rep)\b", PRODUCT_SUPPORT_AGENT),
    (r"\bjust sales\b", PRODUCT_SALES_AGENT),
    (r"\bonly sales\b", PRODUCT_SALES_AGENT),
    (r"\bonly need sales\b", PRODUCT_SALES_AGENT),
    (r"\bjust need sales\b", PRODUCT_SALES_AGENT),
    (r"\bjust support\b", PRODUCT_SUPPORT_AGENT),
    (r"\bonly support\b", PRODUCT_SUPPORT_AGENT),
    (r"\bonly need support\b", PRODUCT_SUPPORT_AGENT),
    (r"\bjust need support\b", PRODUCT_SUPPORT_AGENT),
)

# ---------- corrections ----------

_REMOVE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bremove (hausa|igbo|yoruba|pidgin|english)\b", "language"),
    (r"\bremove (whatsapp|telegram|email|website|web)\b", "channel"),
    (r"\b(no|not|without|don'?t (need|want|use)) (whatsapp|telegram|email)\b", "channel"),
    (r"\bdrop (hausa|igbo|yoruba|pidgin|english|whatsapp|telegram)\b", "any"),
    (r"\bwebsite[- ]only\b", "channel"),
    (r"\bwhatsapp[- ]only\b", "channel"),
    (r"\b(i said|i told you) ([^.!?]{3,60})\b", "correction"),
)

# ---------- intents ----------

_INTENT_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(how much|what(?:'?s| is) the (price|cost|damage)|price it|what does it cost|give me (a )?(price|quote)|quote me)\b", "wants_pricing"),
    (r"\b(what do you (recommend|suggest)|what should i (use|take|get)|which (one|product) (should|fits|is right)|recommend)\b", "wants_recommendation"),
    (r"\b(what have i (selected|chosen|picked)|what'?s (my|the) (current )?(selection|configuration|setup)|what did i (select|choose|pick))\b", "wants_summary"),
    (r"\b(start over|start again|begin again|reset)\b", "wants_reset"),
    (r"\b(change|edit|update|modify) (that|it|my)\b", "wants_change"),
    (r"\b(why|explain|what do you mean|what does .* mean|tell me more about|elaborate)\b", "wants_explanation"),
    (r"\b(what'?s included|what do i get|what comes with)\b", "wants_inclusions"),
    (r"\b(add|also (add|include|want)) (telegram|whatsapp|email|website)\b", "wants_add"),
    (r"\b(i (also )?need support too|i want support too|add support)\b", "wants_add_support"),
    (r"\b(continue|go ahead|carry on|next|proceed|okay|ok|okay|ready|done|yes|yeah|yep|sure)\b", "wants_continue"),
)


def extract_business_facts(text: str, memory: ConversationMemory) -> None:
    """Read business facts out of a message into memory.

    Idempotent and conservative: only records what a pattern actually matched,
    never invents, and never overwrites a stronger provenance with a weaker.
    """
    lowered = (text or "").lower().strip()
    if not lowered:
        return

    for pattern, kind in _BUSINESS_TYPE_PATTERNS:
        if re.search(pattern, lowered):
            memory.remember("business", "business_type", kind, provenance=EXTRACTED)
            break

    for pattern, key in _SOLD_PATTERNS:
        m = re.search(pattern, lowered)
        if m:
            memory.remember(
                "business", "sells", m.group(1).strip(), provenance=EXTRACTED
            )
            break

    for pattern, channel in _CHANNEL_FACT_PATTERNS:
        if re.search(pattern, lowered):
            existing = memory.fact("business", "where_customers_reach_us") or ""
            channels = [c.strip() for c in existing.split(",") if c.strip()]
            if channel not in channels:
                channels.append(channel)
            memory.remember(
                "business",
                "where_customers_reach_us",
                ", ".join(channels),
                provenance=EXTRACTED,
            )

    for pattern, pain in _PAIN_PATTERNS:
        if re.search(pattern, lowered):
            memory.remember("business", "pain", pain, provenance=EXTRACTED)

    for pattern, goal in _GOAL_PATTERNS:
        if re.search(pattern, lowered):
            # Goals accumulate: "I want it to sell" and later "also answer
            # questions" are two requirements, not one replacing the other.
            existing = memory.fact("requirements", "goal") or ""
            goals = [g.strip() for g in existing.split(",") if g.strip()]
            if goal not in goals:
                goals.append(goal)
            memory.remember(
                "requirements",
                "goal",
                ", ".join(goals),
                provenance=EXTRACTED,
            )


def extract_products_mentioned(text: str) -> list[str]:
    """Canonical product codes the buyer named in this message."""
    lowered = (text or "").lower()
    found: list[str] = []
    for pattern, code in _PRODUCT_MENTIONS:
        if re.search(pattern, lowered) and code not in found:
            found.append(code)
    return [c for c in PRODUCT_ORDER if c in found]


def detect_intent(text: str) -> str | None:
    """The buyer's conversational intent, or None when nothing matched.

    Ordered: the first matching intent wins, and the list is arranged so the
    most specific (pricing, recommendation) beat the generic (continue).
    """
    lowered = (text or "").lower().strip()
    if not lowered:
        return None
    for pattern, intent in _INTENT_PATTERNS:
        if re.search(pattern, lowered):
            return intent
    return None


def detect_correction(text: str) -> dict | None:
    """A correction the buyer made to previously-given information.

    Returns a dict describing what to correct, or None. Corrections carry
    ``stated`` provenance — they always win over earlier extractions.
    """
    lowered = (text or "").lower().strip()
    if not lowered:
        return None

    # "Actually remove Hausa" / "remove WhatsApp"
    m = re.search(
        r"\b(?:actually\s+)?(?:remove|drop|delete|take out)\s+"
        r"(hausa|igbo|yoruba|pidgin|nigerian pidgin|english)\b",
        lowered,
    )
    if m:
        name = m.group(1)
        code = next((c for c, n in LANGUAGES.items() if name in n.lower()), None)
        return {"kind": "language", "remove": code} if code else None

    m = re.search(
        r"\b(?:actually\s+)?(?:remove|drop|delete|take out|no|not|without)\s+"
        r"(whatsapp|telegram|email|website|web)\b",
        lowered,
    )
    if m:
        name = m.group(1)
        code = {"website": CHANNEL_WEB, "web": CHANNEL_WEB}.get(
            name, name if name in (CHANNEL_WHATSAPP, CHANNEL_TELEGRAM, CHANNEL_EMAIL) else None
        )
        return {"kind": "channel", "remove": code} if code else None

    # "website-only" / "whatsapp only"
    m = re.search(r"\b(website|web|whatsapp|telegram)[- ]only\b", lowered)
    if m:
        name = m.group(1)
        code = {"website": CHANNEL_WEB, "web": CHANNEL_WEB, "whatsapp": CHANNEL_WHATSAPP, "telegram": CHANNEL_TELEGRAM}.get(name)
        return {"kind": "channel", "only": code} if code else None

    # "I said 12,000"
    m = re.search(r"\bi said\s+([\d,]+)\s*(k)?\b", lowered)
    if m:
        digits = m.group(1).replace(",", "")
        value = int(digits) * (1000 if m.group(2) else 1)
        return {"kind": "volume", "value": value}

    # "add Telegram" / "also need support too"
    m = re.search(r"\b(?:add|also (?:add|include|want))\s+(telegram|whatsapp|email|website|web)\b", lowered)
    if m:
        name = m.group(1)
        code = {"website": CHANNEL_WEB, "web": CHANNEL_WEB}.get(name, name)
        return {"kind": "channel", "add": code}

    return None


def is_question(text: str) -> bool:
    """Does this message ask something rather than answer something?"""
    t = (text or "").strip()
    if not t:
        return False
    if t.endswith("?"):
        return True
    return bool(
        re.search(
            r"^\s*(what|why|how|when|where|who|which|can|could|does|do|is|are|"
            r"will|would|should|tell me|explain)\b",
            t.lower(),
        )
    )

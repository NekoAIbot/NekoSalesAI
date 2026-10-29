"""Wire formats for the sales conversation API.

The visitor-facing shapes never expose the integer conversation id or the
organization id — a public chat widget gets the opaque token and nothing else.
"""

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.sales.reasoning import Reasoning


def sanitize_customer_body(text: str) -> str:
    """Sanitize any model output before returning to customer or saving to conversation.
    Strips chain-of-thought, thinking tags, internal planning, prompt leaks,
    unclosed tags, and malformed internal blocks.
    """
    if not text:
        return ""

    # 1. Strip paired thinking / reasoning / scratchpad / internal tags
    cleaned = re.sub(
        r"<(think|thought|reasoning|scratchpad|internal)>[\s\S]*?</\1>",
        "",
        text,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\[(think|thought|reasoning|scratchpad|internal)\][\s\S]*?\[/\1\]",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    # 2. Strip unclosed opening tags that run to the end of the string (e.g. truncated streaming)
    cleaned = re.sub(
        r"<(think|thought|reasoning|scratchpad|internal)>[\s\S]*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\[(think|thought|reasoning|scratchpad|internal)\][\s\S]*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    # 3. Strip any stray dangling tag remnants
    cleaned = re.sub(
        r"</?(think|thought|reasoning|scratchpad|internal)>",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\[/?(think|thought|reasoning|scratchpad|internal)\]",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    # 4. Strip untagged debug/internal prefixes if model hallucinated internal monologue labels
    cleaned = re.sub(
        r"(?m)^(?:Internal\s+(?:Reasoning|Monologue|Thoughts?)|System\s+Prompt|Rule\s+Evaluation):\s*.*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    return cleaned.strip()


class ReasoningOut(BaseModel):
    """Why the agent said something. Shown to the visitor and to staff.

    There is no confidence field here on purpose: the agent does not produce
    a number it cannot substantiate.
    """

    rule: str
    signals: list[str] = Field(default_factory=list)
    grounded_in: list[str] = Field(default_factory=list)
    escalated: bool = False

    @classmethod
    def from_json(cls, raw: str | None) -> "ReasoningOut | None":
        reasoning = Reasoning.from_json(raw)

        if reasoning is None:
            return None

        return cls(**reasoning.to_dict())


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    body: str
    created_at: datetime
    reasoning: ReasoningOut | None = None

    @classmethod
    def from_model(cls, message, include_reasoning: bool = False) -> "MessageOut":
        sanitized = sanitize_customer_body(message.body) if message.role == "agent" else message.body
        return cls(
            id=message.id,
            role=message.role,
            body=sanitized,
            created_at=message.created_at,
            reasoning=ReasoningOut.from_json(message.reasoning_json) if include_reasoning else None,
        )


class ConversationStart(BaseModel):
    """Opening a thread needs nothing from the visitor."""


class ConversationOut(BaseModel):
    """The thread as the visitor's own browser sees it.

    Carries back the details the visitor gave and the plan they landed on, so
    the checkout form can be a confirmation rather than a second
    interrogation. Still no integer id and no organization id — the token is
    the only handle the widget gets.
    """

    token: str
    stage: str
    visitor_name: str | None = None
    visitor_email: str | None = None
    visitor_company: str | None = None
    interested_plan_code: str | None = None
    messages: list[MessageOut] = Field(default_factory=list)

    @classmethod
    def from_model(cls, conversation, messages, include_reasoning: bool = False) -> "ConversationOut":
        return cls(
            token=conversation.public_token,
            stage=conversation.stage,
            visitor_name=conversation.visitor_name,
            visitor_email=conversation.visitor_email,
            visitor_company=conversation.visitor_company,
            interested_plan_code=conversation.interested_plan_code,
            messages=[MessageOut.from_model(m, include_reasoning=include_reasoning) for m in messages],
        )


class VisitorMessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=4_000)


class VisitorDetailsIn(BaseModel):
    name: str | None = Field(default=None, max_length=150)
    email: EmailStr | None = None
    company: str | None = Field(default=None, max_length=255)


class ConversationCheckoutIn(BaseModel):
    """Raising a payment from inside a conversation.

    Every field is optional because the conversation already knows most of
    them. There is no amount field here either — the price is computed
    server-side from a catalog plan or a stored quote, wherever the checkout
    was started from.
    """

    plan_code: str | None = Field(default=None, max_length=50)
    quote_reference: str | None = Field(default=None, max_length=64)
    email: EmailStr | None = None
    name: str | None = Field(default=None, max_length=150)
    company: str | None = Field(default=None, max_length=255)


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    subject: str
    requested: str
    status: str
    resolution: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None


class ApprovalDecisionIn(BaseModel):
    approve: bool

    # Required in both directions. Declining still owes the visitor an
    # answer, and the agent has none of its own to give.
    resolution: str = Field(min_length=1, max_length=4_000)


class ConversationSummaryOut(BaseModel):
    """Row in the staff-facing conversation list."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    token: str
    stage: str
    visitor_name: str | None = None
    visitor_email: str | None = None
    visitor_company: str | None = None
    interested_plan_code: str | None = None
    lead_id: int | None = None
    is_handed_off: bool = False
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, conversation) -> "ConversationSummaryOut":
        return cls(
            id=conversation.id,
            token=conversation.public_token,
            stage=conversation.stage,
            visitor_name=conversation.visitor_name,
            visitor_email=conversation.visitor_email,
            visitor_company=conversation.visitor_company,
            interested_plan_code=conversation.interested_plan_code,
            lead_id=conversation.lead_id,
            is_handed_off=conversation.is_handed_off,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )


class CheckoutLinkOut(BaseModel):
    """The payment link a conversation earned, as the widget returns it."""

    checkout_url: str
    amount_minor: int
    currency: str
    plan_name: str
    billing_period: str
    message: str


class ConversationStatusOut(BaseModel):
    """Whether a conversation has a price, a link, or still needs intake."""

    stage: str
    has_price: bool
    has_payment_link: bool
    visitor_email: str | None = None
    visitor_name: str | None = None
    payment_link: str | None = None
    payment_amount_minor: int | None = None
    payment_currency: str | None = None
    payment_plan_name: str | None = None
    payment_billing_period: str | None = None

"""What intake gives back: the config as stored, plus what it cannot yet do.

Separate from ``app.schemas.intake`` because the shapes differ on purpose. The
response reports provenance and readiness, neither of which a customer submits.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.models.workspace_profile import WorkspaceProfile
from app.products.config import ROLE_LABELS, ProductConfig, format_money


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    audience: str
    currency: str
    amount_minor: int
    display_price: str
    billing_period: str
    seats: int
    monthly_conversation_limit: int
    features: tuple[str, ...]
    is_default: bool


class CapabilityOut(BaseModel):
    """A claim and, plainly, who vouches for it."""

    claim: str
    source: str
    verified_by: str = ""


class QuestionAnswerOut(BaseModel):
    question: str
    answer: str


class ConfigOut(BaseModel):
    """A product config as the customer's own dashboard sees it."""

    company_name: str
    tagline: str
    description: str
    support_email: str
    agent_name: str

    # Which agent this is, and therefore what it is allowed to do. Read-only
    # here by design: the role was decided by what the customer paid for, and a
    # settings form that could change it would be a customer granting their own
    # support agent permission to quote prices and take money. Reported so the
    # page can stop offering a discount ceiling to an agent that cannot discount.
    role: str

    plans: tuple[PlanOut, ...]
    capabilities: tuple[CapabilityOut, ...]
    faqs: tuple[QuestionAnswerOut, ...]
    knowledge: tuple[QuestionAnswerOut, ...]

    max_auto_discount_percent: int

    # False while the config names no plans. The agent escalates to a human
    # instead of quoting, so surfacing this is how the customer learns their
    # product is not finished rather than discovering it from a buyer.
    sells_anything: bool

    @classmethod
    def from_config(cls, config: ProductConfig) -> ConfigOut:
        return cls(
            company_name=config.company_name,
            tagline=config.tagline,
            description=config.description,
            support_email=config.support_email,
            agent_name=config.agent_name,
            role=config.role,
            plans=tuple(
                PlanOut(
                    code=plan.code,
                    name=plan.name,
                    audience=plan.audience,
                    currency=plan.currency,
                    amount_minor=plan.amount_minor,
                    display_price=format_money(plan.amount_minor, plan.currency),
                    billing_period=plan.billing_period,
                    seats=plan.seats,
                    monthly_conversation_limit=plan.monthly_conversation_limit,
                    features=plan.features,
                    is_default=plan.is_default,
                )
                for plan in config.plans
            ),
            capabilities=tuple(
                CapabilityOut(
                    claim=capability.claim,
                    source=capability.source,
                    verified_by=capability.verified_by,
                )
                for capability in config.capabilities
            ),
            faqs=tuple(
                QuestionAnswerOut(question=f.question, answer=f.answer)
                for f in config.faqs
            ),
            knowledge=tuple(
                QuestionAnswerOut(question=k.question, answer=k.answer)
                for k in config.knowledge
            ),
            max_auto_discount_percent=config.max_auto_discount_percent,
            sells_anything=config.sells_anything,
        )


class AgentOut(BaseModel):
    """One agent in a workspace, as its owner's settings page lists it.

    Exists so a customer who bought both products can be shown both. Their
    delivery email names what they bought in prose; nothing in it tells a form
    which role strings to send, and guessing wrong is how the earlier
    ``.first()`` bugs configured the wrong agent silently.

    ``widget_token`` is here deliberately. It is public by construction — it sits
    in the page source of the customer's own site — and it is the one thing they
    need in hand to install what they bought. Withholding it here would mean the
    only copy lives in an email they may have lost. The secret ``X-API-Key`` is a
    different credential and is not on this model.
    """

    role: str
    label: str
    agent_name: str
    company_name: str
    widget_token: str
    status: str

    # Whether this agent may talk about buying at all. The discount ceiling and
    # the plans list are meaningless for one that cannot, so the page hides them
    # rather than collecting settings that would never be read.
    can_sell: bool

    # True once this agent has something substantive to say. False is the state
    # every freshly provisioned agent starts in, and saying so is the point: it
    # is why the page exists and what the customer has to fix.
    configured: bool

    @classmethod
    def from_profile(cls, profile: WorkspaceProfile, config: ProductConfig) -> AgentOut:
        return cls(
            role=profile.role,
            label=ROLE_LABELS.get(profile.role, profile.role),
            agent_name=profile.agent_name,
            company_name=profile.company_name,
            widget_token=profile.widget_token or "",
            status=profile.status,
            can_sell=config.can_sell,
            configured=bool(
                config.plans
                or config.capabilities
                or config.faqs
                or config.knowledge
            ),
        )


class QuestionOut(BaseModel):
    """The next thing to ask the customer, and what a usable answer looks like."""

    key: str
    prompt: str
    help_text: str
    optional: bool
    multiline: bool

class InterviewOut(BaseModel):
    """Where the interview stands: what to ask, or what went wrong.

    ``error`` is set when an answer already given could not be parsed. The
    caller shows it and re-asks ``question`` rather than advancing, which is
    how a price we could not read becomes a re-ask instead of a stored guess.
    """

    question: QuestionOut | None = None
    error: str = ""
    complete: bool = False

    # The config the answers so far would produce. None while the answers
    # cannot yet build one, so a customer can see their product taking shape
    # without it being saved.
    preview: ConfigOut | None = None

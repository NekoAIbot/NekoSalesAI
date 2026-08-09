"""What intake gives back: the config as stored, plus what it cannot yet do.

Separate from ``app.schemas.intake`` because the shapes differ on purpose. The
response reports provenance and readiness, neither of which a customer submits.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.products.config import ProductConfig, format_money


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

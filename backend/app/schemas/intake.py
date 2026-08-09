"""Requirements intake: the wire format a customer describes their product in.

This is the front door of the factory. A customer says what their AI should
know, sell and claim; the result is a ``ProductConfig`` saved to their
workspace and read by the engine on every reply.

Everything arriving here is customer-supplied, which sets two rules.

**Money is parsed, never floated.** The form carries a human decimal like
``18500.50``. It is converted to integer minor units through ``Decimal``, so
the amount the customer typed is the amount the engine quotes and the amount
Paystack charges. A float would make some prices unrepresentable.

**A customer cannot mark their own claim verified.** ``verified_by`` is not a
field here and there is no way to ask for one. Every capability that comes
through intake is DECLARED, so the agent attributes it rather than asserting
it in our voice. That is the whole reason ``Capability.source`` exists.

Nothing in this module invents content. An intake that names no plans produces
a config that sells nothing, and the agent escalates to a human instead of
quoting a figure nobody set.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.products.config import (
    SOURCE_DECLARED,
    Capability,
    Faq,
    Plan,
    ProductConfig,
)

# Currencies we can actually take money in. Paystack settles NGN; USD is
# quotable. An unlisted currency is rejected rather than quoted, because a
# price the checkout cannot charge is a fabricated price.
SUPPORTED_CURRENCIES = ("NGN", "USD")

# Billing periods the agent has phrasing for. "visit" and "project" cover
# one-off work, which a clinic or an agency needs and a SaaS tier does not.
BILLING_PERIODS = ("month", "year", "visit", "project", "once")

# Caps exist so one submission cannot store an unbounded row. Generous enough
# that no honest intake hits them.
MAX_PLANS = 12
MAX_ITEMS = 40
MAX_FEATURES = 20


class PlanIn(BaseModel):
    """One thing the customer sells, priced in their own currency."""

    model_config = ConfigDict(str_strip_whitespace=True)

    code: str = Field(min_length=1, max_length=60, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=120)
    audience: str = Field(default="", max_length=300)
    currency: str = Field(default="NGN")
    amount: Decimal = Field(ge=0, le=Decimal("99999999.99"))
    billing_period: str = Field(default="month")
    seats: int = Field(default=1, ge=0, le=10_000)
    monthly_conversation_limit: int = Field(default=0, ge=0, le=10_000_000)
    features: tuple[str, ...] = ()
    is_default: bool = False

    @field_validator("currency")
    @classmethod
    def _known_currency(cls, value: str) -> str:
        upper = value.upper()

        if upper not in SUPPORTED_CURRENCIES:
            raise ValueError(
                f"{value!r} is not a currency we can charge in. "
                f"Supported: {', '.join(SUPPORTED_CURRENCIES)}."
            )

        return upper

    @field_validator("billing_period")
    @classmethod
    def _known_period(cls, value: str) -> str:
        lower = value.lower()

        if lower not in BILLING_PERIODS:
            raise ValueError(
                f"{value!r} is not a billing period the agent can phrase. "
                f"Supported: {', '.join(BILLING_PERIODS)}."
            )

        return lower

    @field_validator("features")
    @classmethod
    def _bounded_features(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        kept = tuple(f.strip() for f in value if f.strip())

        if len(kept) > MAX_FEATURES:
            raise ValueError(f"A plan may list at most {MAX_FEATURES} features.")

        return kept

    @property
    def amount_minor(self) -> int:
        """Exact minor units. Integer arithmetic on a Decimal, never a float."""
        try:
            quantized = self.amount.quantize(Decimal("0.01"))
        except InvalidOperation as exc:  # pragma: no cover - Field caps the range
            raise ValueError(f"{self.amount} is not a usable amount.") from exc

        return int(quantized * 100)

    def to_plan(self) -> Plan:
        return Plan(
            code=self.code,
            name=self.name,
            audience=self.audience,
            currency=self.currency,
            amount_minor=self.amount_minor,
            billing_period=self.billing_period,
            seats=self.seats,
            monthly_conversation_limit=self.monthly_conversation_limit,
            features=self.features,
            is_default=self.is_default,
        )


class QuestionAnswerIn(BaseModel):
    """A question the customer's buyers ask, and the answer they want given."""

    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=300)
    answer: str = Field(min_length=1, max_length=2_000)

    def to_faq(self) -> Faq:
        return Faq(question=self.question, answer=self.answer)


class IntakeIn(BaseModel):
    """A customer's description of the AI product they want.

    The fields are deliberately the shape of a ``ProductConfig`` rather than
    free prose. Stage B2 adds a conversational intake that fills this in; the
    structured form stays the thing that gets validated and stored, so there
    is exactly one place where customer text becomes product behaviour.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    company_name: str = Field(min_length=1, max_length=120)
    tagline: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=2_000)
    support_email: str = Field(default="", max_length=200)
    # Capped at 100 to match WorkspaceProfile.agent_name's column, which the
    # save mirrors. A longer name would be a 422 here or a truncation there.
    agent_name: str = Field(default="", max_length=100)

    plans: tuple[PlanIn, ...] = ()

    # Free-text claims about the customer's business. Stored as DECLARED, with
    # no way to request otherwise.
    capabilities: tuple[str, ...] = ()

    faqs: tuple[QuestionAnswerIn, ...] = ()
    knowledge: tuple[QuestionAnswerIn, ...] = ()

    max_auto_discount_percent: int = Field(default=0, ge=0, le=100)

    @field_validator("plans")
    @classmethod
    def _bounded_unique_plans(cls, value: tuple[PlanIn, ...]) -> tuple[PlanIn, ...]:
        if len(value) > MAX_PLANS:
            raise ValueError(f"At most {MAX_PLANS} plans per product.")

        codes = [plan.code for plan in value]
        duplicates = sorted({c for c in codes if codes.count(c) > 1})

        if duplicates:
            # Caught here as a 422 rather than in ProductConfig as a 500. Two
            # plans sharing a code would make a quote and its payment link
            # disagree about the price.
            raise ValueError(f"Duplicate plan codes: {duplicates}.")

        return value

    @field_validator("capabilities")
    @classmethod
    def _bounded_capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        kept = tuple(c.strip() for c in value if c.strip())

        if len(kept) > MAX_ITEMS:
            raise ValueError(f"At most {MAX_ITEMS} capabilities.")

        return kept

    @field_validator("faqs", "knowledge")
    @classmethod
    def _bounded_pairs(
        cls, value: tuple[QuestionAnswerIn, ...]
    ) -> tuple[QuestionAnswerIn, ...]:
        if len(value) > MAX_ITEMS:
            raise ValueError(f"At most {MAX_ITEMS} entries.")

        return value

    def to_config(self) -> ProductConfig:
        """Build the config the engine will read.

        Every capability is DECLARED. There is no branch here that produces a
        verified one, because nothing in this repo implements a claim about
        someone else's business.
        """
        return ProductConfig(
            company_name=self.company_name,
            tagline=self.tagline,
            description=self.description,
            support_email=self.support_email,
            agent_name=self.agent_name or self.company_name,
            plans=tuple(plan.to_plan() for plan in self.plans),
            capabilities=tuple(
                Capability(claim=claim, source=SOURCE_DECLARED)
                for claim in self.capabilities
            ),
            faqs=tuple(faq.to_faq() for faq in self.faqs),
            knowledge=tuple(fact.to_faq() for fact in self.knowledge),
            max_auto_discount_percent=self.max_auto_discount_percent,
        )

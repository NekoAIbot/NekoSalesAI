"""Wire formats for checkout and provisioning.

Two things are deliberately absent from every response here. The API key
appears exactly once, in the response to the request that created it, and
never in any subsequent read — there is no endpoint that will hand it back.
And no schema carries the raw Paystack payload out to a client; it is
evidence, kept server-side.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.workspace_profile import PROVISION_STEPS, STEP_LABELS


class CheckoutRequest(BaseModel):
    """What the buyer supplies to start a checkout.

    Notably not an amount. A ``plan_code`` is priced from the catalog and a
    ``quote_reference`` is re-priced from the requirement the server stored, so
    there is no field here a buyer could use to name their own price. Send one
    or the other; the service refuses both at once.
    """

    plan_code: str | None = Field(default=None, min_length=1, max_length=50)
    quote_reference: str | None = Field(default=None, min_length=1, max_length=64)
    email: EmailStr
    name: str | None = Field(default=None, max_length=150)
    company: str | None = Field(default=None, max_length=255)


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reference: str
    status: str
    plan_code: str
    plan_name: str
    billing_period: str
    amount_minor: int
    currency: str
    display_amount: str
    checkout_url: str | None = None
    buyer_email: str
    paid_at: datetime | None = None

    @classmethod
    def from_model(cls, order) -> "OrderOut":
        from app.catalog import format_money

        return cls(
            reference=order.paystack_reference,
            status=order.status,
            plan_code=order.plan_code,
            plan_name=order.plan_name,
            billing_period=order.billing_period,
            amount_minor=order.amount_minor,
            currency=order.currency,
            display_amount=format_money(order.amount_minor, order.currency),
            checkout_url=order.checkout_url,
            buyer_email=order.buyer_email,
            paid_at=order.paid_at,
        )


class ProvisionStepOut(BaseModel):
    """One step of standing up a workspace, and when it finished."""

    key: str
    label: str
    done: bool
    completed_at: str | None = None


class WorkspaceOut(BaseModel):
    """The customer's workspace as the provisioning screen sees it."""

    status: str
    plan_code: str
    company_name: str
    agent_name: str
    widget_token: str | None = None
    api_key_prefix: str | None = None
    steps: list[ProvisionStepOut] = Field(default_factory=list)
    ready_at: datetime | None = None
    failure_reason: str | None = None

    # Present only in the response that provisioned the workspace. A second
    # read of the same workspace will not include them, because the server
    # kept only a hash of the key and never stored the password at all.
    api_key: str | None = None
    temporary_password: str | None = None

    @classmethod
    def from_model(
        cls,
        profile,
        api_key: str | None = None,
        temporary_password: str | None = None,
    ) -> "WorkspaceOut":
        import json

        try:
            stamps = json.loads(profile.steps_json) if profile.steps_json else {}
        except ValueError:
            stamps = {}

        return cls(
            status=profile.status,
            plan_code=profile.plan_code,
            company_name=profile.company_name,
            agent_name=profile.agent_name,
            widget_token=profile.widget_token,
            api_key_prefix=profile.api_key_prefix,
            steps=[
                ProvisionStepOut(
                    key=step,
                    label=STEP_LABELS[step],
                    done=step in stamps,
                    completed_at=stamps.get(step),
                )
                for step in PROVISION_STEPS
            ],
            ready_at=profile.ready_at,
            failure_reason=profile.failure_reason,
            api_key=api_key,
            temporary_password=temporary_password,
        )


class CheckoutStatusOut(BaseModel):
    """What the return page polls: is it paid, and is it built yet."""

    order: OrderOut
    workspace: WorkspaceOut | None = None


class WorkspaceSettingsIn(BaseModel):
    """The short form a customer fills in to configure their agent."""

    agent_name: str | None = Field(default=None, min_length=1, max_length=100)
    company_name: str | None = Field(default=None, min_length=1, max_length=150)
    greeting: str | None = Field(default=None, min_length=1, max_length=2_000)
    tone: str | None = Field(default=None, max_length=40)
    accent_color: str | None = Field(default=None, max_length=20)

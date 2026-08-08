"""Wire formats for the post-sale follow-up queue.

Staff-facing only. A follow-up carries the customer's contact details and the
message about to go to them, so none of these shapes are ever served to a
visitor.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.sales import ReasoningOut


class FollowUpOut(BaseModel):
    """One scheduled message, as the sales desk sees it.

    Carries the reasoning alongside the body deliberately: whoever is about to
    send this should be able to see which rule scheduled it and what it read,
    without having to go and find the code.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_code: str
    day_offset: int
    due_at: datetime
    status: str
    subject: str
    body: str
    recipient: str | None = None
    company_name: str | None = None
    sent_at: datetime | None = None
    cancelled_reason: str | None = None
    reasoning: ReasoningOut | None = None

    @classmethod
    def from_model(
        cls,
        follow_up,
        recipient: str | None = None,
        company_name: str | None = None,
    ) -> "FollowUpOut":
        return cls(
            id=follow_up.id,
            rule_code=follow_up.rule_code,
            day_offset=follow_up.day_offset,
            due_at=follow_up.due_at,
            status=follow_up.status,
            subject=follow_up.subject,
            body=follow_up.body,
            recipient=recipient,
            company_name=company_name,
            sent_at=follow_up.sent_at,
            cancelled_reason=follow_up.cancelled_reason,
            reasoning=ReasoningOut.from_json(follow_up.reasoning_json),
        )


class FollowUpCancelIn(BaseModel):
    """Cancelling owes a reason, the same as declining an approval does."""

    reason: str = Field(min_length=1, max_length=255)

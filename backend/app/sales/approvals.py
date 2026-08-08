"""Approval-gate operations.

Kept separate from the conversation service because the two have different
audiences: the conversation service serves an anonymous visitor, this serves
an authenticated human deciding what the business will commit to.
"""

# Deferred for the same reason as in sales/service.py: the ``list`` method on
# this class shadows the builtin inside the class body.
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.approval_request import (
    STATUS_APPROVED,
    STATUS_DECLINED,
    STATUS_PENDING,
    ApprovalRequest,
)
from app.models.conversation import (
    ROLE_HUMAN,
    STAGE_AWAITING_APPROVAL,
    STAGE_NEGOTIATING,
    Conversation,
    Message,
)
from app.sales.reasoning import Reasoning


class ApprovalError(ValueError):
    """Raised when a decision cannot be applied as asked."""


class ApprovalService:

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        conversation: Conversation,
        subject: str,
        requested: str,
    ) -> ApprovalRequest:
        request = ApprovalRequest(
            organization_id=conversation.organization_id,
            conversation_id=conversation.id,
            subject=subject,
            requested=requested,
            status=STATUS_PENDING,
        )

        self.db.add(request)
        conversation.stage = STAGE_AWAITING_APPROVAL

        self.db.commit()
        self.db.refresh(request)

        return request

    def list(
        self,
        organization_id: int,
        status: str | None = None,
    ) -> list[ApprovalRequest]:
        query = self.db.query(ApprovalRequest).filter(
            ApprovalRequest.organization_id == organization_id
        )

        if status:
            query = query.filter(ApprovalRequest.status == status)

        return query.order_by(ApprovalRequest.created_at.desc()).all()

    def get(
        self,
        organization_id: int,
        request_id: int,
    ) -> ApprovalRequest | None:
        return (
            self.db.query(ApprovalRequest)
            .filter(
                ApprovalRequest.id == request_id,
                ApprovalRequest.organization_id == organization_id,
            )
            .first()
        )

    def pending_count(self, organization_id: int) -> int:
        return (
            self.db.query(ApprovalRequest)
            .filter(
                ApprovalRequest.organization_id == organization_id,
                ApprovalRequest.status == STATUS_PENDING,
            )
            .count()
        )

    def decide(
        self,
        request: ApprovalRequest,
        approve: bool,
        resolution: str,
        user_id: int | None = None,
    ) -> ApprovalRequest:
        """Record a human decision and post the answer into the thread.

        The resolution text is posted verbatim as a ``human`` message. It is
        not paraphrased or re-generated, because the whole point of the gate
        is that a person authored the commitment the visitor receives.
        """
        if not request.is_pending:
            raise ApprovalError(
                f"Request {request.id} was already {request.status}."
            )

        resolution = (resolution or "").strip()

        if not resolution:
            # Approving with no answer would send the agent back to the
            # visitor with nothing true to say.
            raise ApprovalError(
                "A decision needs a reply for the visitor. Say what they "
                "should be told."
            )

        request.status = STATUS_APPROVED if approve else STATUS_DECLINED
        request.resolution = resolution
        request.resolved_by_user_id = user_id
        request.resolved_at = datetime.now(timezone.utc)

        reasoning = Reasoning(
            rule="human_decision",
            signals=[
                f"approval request {request.id} "
                f"{'approved' if approve else 'declined'} by a human"
            ],
            grounded_in=[f"approval:{request.id}"],
        )

        self.db.add(
            Message(
                conversation_id=request.conversation_id,
                role=ROLE_HUMAN,
                body=resolution,
                reasoning_json=reasoning.to_json(),
            )
        )

        conversation = (
            self.db.query(Conversation)
            .filter(Conversation.id == request.conversation_id)
            .first()
        )

        # Only move the thread on if it is still parked on this gate. A later
        # message may already have advanced it, and reversing that would
        # silently undo the visitor's progress.
        if conversation and conversation.stage == STAGE_AWAITING_APPROVAL:
            conversation.stage = STAGE_NEGOTIATING

        self.db.commit()
        self.db.refresh(request)

        return request

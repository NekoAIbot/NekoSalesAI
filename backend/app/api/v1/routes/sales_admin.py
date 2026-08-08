"""Staff-facing sales API: the approval queue and conversation review.

Every route here is authenticated and scoped to the caller's organization.
That scoping is the tenant boundary — a user must not be able to read another
company's buyer conversations by guessing an id, so the organization filter
lives in the query rather than in a post-fetch check.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.dependencies.database import get_db
from app.models.approval_request import STATUS_PENDING
from app.models.user import User
from app.schemas.sales import (
    ApprovalDecisionIn,
    ApprovalOut,
    ConversationOut,
    ConversationSummaryOut,
)
from app.sales.approvals import ApprovalError, ApprovalService
from app.sales.service import ConversationService

router = APIRouter(
    prefix="/sales-desk",
    tags=["Sales Desk"],
)


@router.get(
    "/conversations",
    response_model=list[ConversationSummaryOut],
)
def list_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversations = ConversationService(db).list(current_user.organization_id)

    return [ConversationSummaryOut.from_model(c) for c in conversations]


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationOut,
)
def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = ConversationService(db)
    conversation = service.get(current_user.organization_id, conversation_id)

    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    return ConversationOut.from_model(
        conversation,
        service.messages(conversation.id),
    )


@router.get(
    "/approvals",
    response_model=list[ApprovalOut],
)
def list_approvals(
    status_filter: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ApprovalService(db).list(
        current_user.organization_id,
        status=status_filter,
    )


@router.get(
    "/approvals/pending-count",
)
def pending_approval_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return {
        "pending": ApprovalService(db).pending_count(
            current_user.organization_id
        )
    }


@router.post(
    "/approvals/{request_id}/decide",
    response_model=ApprovalOut,
)
def decide_approval(
    request_id: int,
    payload: ApprovalDecisionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = ApprovalService(db)
    request = service.get(current_user.organization_id, request_id)

    if request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval request not found.",
        )

    try:
        return service.decide(
            request,
            approve=payload.approve,
            resolution=payload.resolution,
            user_id=current_user.id,
        )
    except ApprovalError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get("/summary")
def desk_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Counts for the dashboard header. Real numbers only — each is a query."""
    conversations = ConversationService(db).list(current_user.organization_id)
    approvals = ApprovalService(db)

    return {
        "conversations": len(conversations),
        "pending_approvals": approvals.pending_count(
            current_user.organization_id
        ),
        "resolved_approvals": len(
            [
                a
                for a in approvals.list(current_user.organization_id)
                if a.status != STATUS_PENDING
            ]
        ),
    }

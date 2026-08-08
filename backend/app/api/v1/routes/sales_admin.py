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
from app.followups.service import FollowUpSendError, FollowUpService
from app.models.approval_request import STATUS_PENDING
from app.models.follow_up import STATUS_SCHEDULED
from app.models.order import Order
from app.models.user import User
from app.models.workspace_profile import WorkspaceProfile
from app.schemas.follow_up import FollowUpCancelIn, FollowUpOut
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
        "follow_ups_due": len(
            FollowUpService(db).due(current_user.organization_id)
        ),
    }


# ---------- post-sale follow-ups ----------


def _decorate(follow_up, db: Session) -> FollowUpOut:
    """Attach who this is going to, for a queue that reads like a queue.

    The recipient lives on the order and the company name on the workspace
    profile, neither of which is on the follow-up row itself.
    """
    profile = db.get(WorkspaceProfile, follow_up.workspace_profile_id)
    order = (
        db.get(Order, follow_up.order_id)
        if follow_up.order_id is not None
        else None
    )

    return FollowUpOut.from_model(
        follow_up,
        recipient=order.buyer_email if order is not None else None,
        company_name=profile.company_name if profile is not None else None,
    )


@router.get(
    "/follow-ups",
    response_model=list[FollowUpOut],
)
def list_follow_ups(
    status_filter: str | None = None,
    due_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The post-sale queue, scoped to the caller's organization."""
    service = FollowUpService(db)

    follow_ups = (
        service.due(current_user.organization_id)
        if due_only
        else service.list(current_user.organization_id, status=status_filter)
    )

    return [_decorate(f, db) for f in follow_ups]


@router.get("/follow-ups/due-count")
def due_follow_up_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return {"due": len(FollowUpService(db).due(current_user.organization_id))}


@router.post(
    "/follow-ups/{follow_up_id}/send",
    response_model=FollowUpOut,
)
def send_follow_up(
    follow_up_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Deliver a follow-up through the configured sender.

    With no sender configured this returns 409 with the reason, rather than
    reporting a send that did not happen. Use the mark-sent endpoint after
    sending it by hand.
    """
    service = FollowUpService(db)
    follow_up = service.get(current_user.organization_id, follow_up_id)

    if follow_up is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Follow-up not found.",
        )

    try:
        return _decorate(service.send(follow_up), db)
    except FollowUpSendError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/follow-ups/{follow_up_id}/mark-sent",
    response_model=FollowUpOut,
)
def mark_follow_up_sent(
    follow_up_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record that a human sent this themselves."""
    service = FollowUpService(db)
    follow_up = service.get(current_user.organization_id, follow_up_id)

    if follow_up is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Follow-up not found.",
        )

    try:
        return _decorate(service.mark_sent_manually(follow_up), db)
    except FollowUpSendError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/follow-ups/{follow_up_id}/cancel",
    response_model=FollowUpOut,
)
def cancel_follow_up(
    follow_up_id: int,
    payload: FollowUpCancelIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = FollowUpService(db)
    follow_up = service.get(current_user.organization_id, follow_up_id)

    if follow_up is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Follow-up not found.",
        )

    if follow_up.status != STATUS_SCHEDULED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This follow-up is already {follow_up.status}.",
        )

    return _decorate(service.cancel(follow_up, payload.reason), db)

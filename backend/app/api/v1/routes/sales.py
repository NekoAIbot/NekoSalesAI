"""Public sales-conversation API.

Unauthenticated by design: this is what the website chat widget talks to. A
visitor holds an opaque conversation token and can only act on their own
thread. Everything staff-facing lives in ``routes/sales_admin.py`` behind
authentication.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.catalog import COMPANY, FAQS, PLANS
from app.config.settings import settings
from app.dependencies.database import get_db
from app.models.conversation import Conversation
from app.repositories.organization_repository import OrganizationRepository
from app.schemas.sales import (
    ConversationOut,
    MessageOut,
    VisitorDetailsIn,
    VisitorMessageIn,
)
from app.sales.service import ConversationError, ConversationService

router = APIRouter(
    prefix="/sales",
    tags=["Sales Conversation"],
)


def _default_organization_id(db: Session) -> int:
    """The org whose product the public site is selling.

    Single-tenant for the public storefront: this deployment sells
    NekoSalesAI itself. Customer-embedded widgets resolve their own org from
    their API key, which is a separate route.
    """
    org = OrganizationRepository(db).get_by_slug(settings.STOREFRONT_ORG_SLUG)

    if org is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sales agent is not configured yet.",
        )

    return org.id


def _load_conversation(token: str, db: Session) -> Conversation:
    conversation = ConversationService(db).get_by_token(token)

    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    return conversation


@router.get("/catalog")
def get_catalog():
    """The published catalog, so the page and the agent cannot disagree."""
    return {
        "company": COMPANY,
        "plans": [
            {
                "code": plan.code,
                "name": plan.name,
                "audience": plan.audience,
                "currency": plan.currency,
                "amount_minor": plan.amount_minor,
                "display_price": plan.display_price,
                "billing_period": plan.billing_period,
                "seats": plan.seats,
                "monthly_conversation_limit": plan.monthly_conversation_limit,
                "features": list(plan.features),
                "is_default": plan.is_default,
            }
            for plan in PLANS
        ],
        "faqs": [
            {"question": faq.question, "answer": faq.answer} for faq in FAQS
        ],
    }


@router.post(
    "/conversations",
    response_model=ConversationOut,
    status_code=status.HTTP_201_CREATED,
)
def start_conversation(db: Session = Depends(get_db)):
    service = ConversationService(db)
    conversation = service.start(_default_organization_id(db))

    return ConversationOut.from_model(
        conversation,
        service.messages(conversation.id),
    )


@router.get(
    "/conversations/{token}",
    response_model=ConversationOut,
)
def get_conversation(token: str, db: Session = Depends(get_db)):
    service = ConversationService(db)
    conversation = _load_conversation(token, db)

    return ConversationOut.from_model(
        conversation,
        service.messages(conversation.id),
    )


@router.post(
    "/conversations/{token}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
def send_message(
    token: str,
    payload: VisitorMessageIn,
    db: Session = Depends(get_db),
):
    service = ConversationService(db)
    conversation = _load_conversation(token, db)

    try:
        reply = service.handle_visitor_message(conversation, payload.body)
    except ConversationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return MessageOut.from_model(reply)


@router.patch(
    "/conversations/{token}/visitor",
    response_model=ConversationOut,
)
def update_visitor(
    token: str,
    payload: VisitorDetailsIn,
    db: Session = Depends(get_db),
):
    service = ConversationService(db)
    conversation = _load_conversation(token, db)

    conversation = service.update_visitor_details(
        conversation,
        name=payload.name,
        email=str(payload.email) if payload.email else None,
        company=payload.company,
    )

    return ConversationOut.from_model(
        conversation,
        service.messages(conversation.id),
    )

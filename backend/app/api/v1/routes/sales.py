"""Public sales-conversation API.

Unauthenticated by design: this is what the website chat widget talks to. A
visitor holds an opaque conversation token and can only act on their own
thread. Everything staff-facing lives in ``routes/sales_admin.py`` behind
authentication.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.catalog import COMPANY, FAQS, STOREFRONT_CONFIG
from app.config.settings import settings
from app.dependencies.database import get_db
from app.models.conversation import Conversation
from app.payments import PaymentsNotConfigured, PaystackError
from app.payments.checkout import CheckoutError, CheckoutService
from app.pricing.quotes import reference_from_plan_code
from app.repositories.organization_repository import OrganizationRepository
from app.schemas.checkout import OrderOut
from app.schemas.sales import (
    ConversationCheckoutIn,
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
    """The published catalog, so the page and the agent cannot disagree.

    ``plans`` is empty for this storefront and stays in the payload rather than
    disappearing from it: the widget reads it to label a fixed plan, and a
    customer's own product may well publish three. What the storefront publishes
    instead is ``pricing``, which says the figure is computed — so a client can
    tell "no tiers" apart from "tiers failed to load" and show the buyer the
    right thing either way.
    """
    return {
        "company": COMPANY,
        "pricing": {
            "mode": STOREFRONT_CONFIG.pricing_mode,
            "quote_endpoint": "/api/v1/pricing/quote",
            "options_endpoint": "/api/v1/pricing/options",
        },
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
            for plan in STOREFRONT_CONFIG.plans
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


@router.post(
    "/conversations/{token}/checkout",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
)
def checkout_from_conversation(
    token: str,
    payload: ConversationCheckoutIn,
    db: Session = Depends(get_db),
):
    """Raise a payment for what this conversation settled on.

    The buyer has already told the agent their email and what they want, so
    asking again would be the conversation forgetting itself. It still has to
    be something the conversation actually reached — a token is not authority
    to buy something never discussed — and the price is computed server-side
    either way: from the catalog for a plan, or by re-pricing the stored
    requirement for a quote.
    """
    conversation = _load_conversation(token, db)

    quote_reference = payload.quote_reference
    plan_code = None if quote_reference else (
        payload.plan_code or conversation.interested_plan_code
    )

    # A build Nera priced in the conversation is remembered as
    # ``quote_<reference>`` in the same column a plan code lives in — one slot,
    # because the buyer settled on exactly one thing. Unwrap it here so the
    # checkout is handed a reference rather than a code that no plan list will
    # ever contain. Without this the widget's own close breaks the moment the
    # storefront stops selling fixed tiers.
    from_quote = reference_from_plan_code(plan_code)
    if from_quote is not None:
        quote_reference = from_quote
        plan_code = None

    if not plan_code and not quote_reference:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No plan or quote has been chosen in this conversation yet.",
        )

    email = str(payload.email) if payload.email else conversation.visitor_email
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An email address is needed before a payment can be raised.",
        )

    # Keep the thread and the order agreeing about who is buying what.
    ConversationService(db).update_visitor_details(
        conversation,
        name=payload.name,
        email=email,
        company=payload.company,
    )

    try:
        order = CheckoutService(db).create_order(
            organization_id=conversation.organization_id,
            plan_code=plan_code,
            quote_reference=quote_reference,
            buyer_email=email,
            buyer_name=payload.name or conversation.visitor_name,
            buyer_company=payload.company or conversation.visitor_company,
            conversation=conversation,
        )
    except PaymentsNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Payments are not switched on for this deployment yet. "
                "Nothing has been charged."
            ),
        ) from exc
    except CheckoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except PaystackError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Our payment provider could not start this checkout. Try again.",
        ) from exc

    return OrderOut.from_model(order)

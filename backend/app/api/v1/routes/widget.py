"""The widget API — a customer's own agent, on a customer's own site.

This is the route ``app.api.v1.routes.sales`` has referred to since it was
written ("customer-embedded widgets resolve their own org from their API key,
which is a separate route") and which did not exist. Provisioning stamped
"Preparing your widget", minted a ``widget_token``, and there was nothing to
present it to. A customer could pay and had no way to put the thing they bought
on their website.

**The token here is not a secret.** It is embedded in the page source of the
customer's site, so anyone who views source can read it. That constrains what it
is allowed to do, and the constraint is the design: a widget token authorises
starting a conversation and reading the branding needed to render the panel. It
cannot reconfigure the workspace, cannot read other conversations, and cannot
reach anything under the authenticated API. The secret ``X-API-Key`` is a
different credential handled in ``app.auth.api_key`` and is never sent to a
browser.

Every conversation started here belongs to the customer's organization, so
``app.products.resolver`` hands the engine that customer's ``ProductConfig`` —
their plans, their claims, their agent name. That is the whole point of Stage A
arriving before this route: no code here decides what the agent says.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.conversation import Conversation
from app.models.workspace_profile import PROVISION_READY, WorkspaceProfile
from app.products.config import ROLE_SALES_AGENT
from app.sales.service import ConversationError, ConversationService
from app.schemas.sales import ConversationOut, MessageOut, VisitorMessageIn

router = APIRouter(
    prefix="/widget",
    tags=["Widget"],
)


def _profile(token: str, db: Session) -> WorkspaceProfile:
    """The workspace a widget token belongs to.

    A token for a workspace that is not ready is refused rather than served a
    half-written config: intake may still be filling in the catalog, and an agent
    answering out of a partial one is the failure ``resolver`` exists to prevent.
    """
    profile = db.execute(
        select(WorkspaceProfile).where(WorkspaceProfile.widget_token == token)
    ).scalars().first()

    # One message for "no such token" and "not ready yet" would be friendlier to
    # debug and would also let anyone enumerate which tokens exist. 404 both ways.
    if profile is None or profile.status != PROVISION_READY:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown widget.",
        )

    return profile


def _conversation(profile: WorkspaceProfile, token: str, db: Session) -> Conversation:
    """A conversation, checked against the widget that is asking for it.

    The ownership check is the part that matters. Conversation tokens are
    unguessable, so this is not the only thing standing between two customers'
    threads — but "unguessable" is a property of the generator, and a route that
    relies on it alone would silently become cross-tenant the day that changes.
    """
    conversation = ConversationService(db).get_by_token(token)

    if conversation is None or conversation.organization_id != profile.organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    return conversation


@router.get("/{widget_token}/config")
def widget_config(widget_token: str, db: Session = Depends(get_db)):
    """What the widget needs to render itself.

    Branding and identity only. No plans, no prices, no knowledge base: the agent
    composes replies server-side, so a widget that received the catalog would be
    holding a copy it has no use for and could disagree with.
    """
    profile = _profile(widget_token, db)

    return {
        "agent_name": profile.agent_name,
        "company_name": profile.company_name,
        "greeting": profile.greeting,
        "accent_color": profile.accent_color,
        # The widget shows a composer either way; this tells it whether to
        # describe the agent as one that can talk about buying.
        "can_sell": profile.role == ROLE_SALES_AGENT,
    }


@router.post(
    "/{widget_token}/conversations",
    response_model=ConversationOut,
    status_code=status.HTTP_201_CREATED,
)
def start_conversation(widget_token: str, db: Session = Depends(get_db)):
    profile = _profile(widget_token, db)

    service = ConversationService(db)
    # The customer's organization, so resolve_config hands the engine the
    # customer's catalog rather than the storefront's.
    conversation = service.start(profile.organization_id)

    return ConversationOut.from_model(
        conversation,
        service.messages(conversation.id),
    )


@router.get(
    "/{widget_token}/conversations/{token}",
    response_model=ConversationOut,
)
def get_conversation(widget_token: str, token: str, db: Session = Depends(get_db)):
    profile = _profile(widget_token, db)
    service = ConversationService(db)
    conversation = _conversation(profile, token, db)

    return ConversationOut.from_model(
        conversation,
        service.messages(conversation.id),
    )


@router.post(
    "/{widget_token}/conversations/{token}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
def send_message(
    widget_token: str,
    token: str,
    payload: VisitorMessageIn,
    db: Session = Depends(get_db),
):
    profile = _profile(widget_token, db)
    service = ConversationService(db)
    conversation = _conversation(profile, token, db)

    try:
        reply = service.handle_visitor_message(conversation, payload.body)
    except ConversationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return MessageOut.from_model(reply)

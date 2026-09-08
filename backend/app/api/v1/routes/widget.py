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

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.logging import get_logger
from app.database.session import get_db
from app.models.conversation import Conversation
from app.models.workspace_profile import PROVISION_READY, WorkspaceProfile
from app.products.config import ROLE_SALES_AGENT
from app.sales.service import ConversationError, ConversationService
from app.schemas.sales import ConversationOut, MessageOut, VisitorMessageIn

logger = get_logger(__name__)

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

    The profile check is the same argument one level in. A workspace can hold two
    agents, and a thread that belongs to the support agent must not be continued
    through the sales widget: the engine would answer it with the other agent's
    identity and the other agent's permission to quote. Threads written before
    that column existed carry no profile and are left continuable, which is the
    old behaviour rather than a hole — they belong to workspaces that had one
    agent for there to be any doubt about.
    """
    conversation = ConversationService(db).get_by_token(token)

    if conversation is None or conversation.organization_id != profile.organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    if (
        conversation.workspace_profile_id is not None
        and conversation.workspace_profile_id != profile.id
    ):
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
    _note_the_widget_ran(profile, db)

    return {
        "agent_name": profile.agent_name,
        "company_name": profile.company_name,
        "greeting": profile.greeting,
        "accent_color": profile.accent_color,
        # The widget shows a composer either way; this tells it whether to
        # describe the agent as one that can talk about buying.
        "can_sell": profile.role == ROLE_SALES_AGENT,
    }


# How stale the last-seen stamp is allowed to get before it is rewritten. The
# value is read to the nearest few minutes when diagnosing an install, so writing
# per page view would charge a busy customer's site for a diagnostic nobody reads
# that precisely.
WIDGET_SEEN_INTERVAL = timedelta(minutes=5)


def _note_the_widget_ran(profile: WorkspaceProfile, db: Session) -> None:
    """Record that the snippet on the customer's site executed.

    This request can only come from a page carrying the snippet, which makes it
    the one thing we can observe about an install without asking. It is what lets
    Nera answer "the chat isn't showing" with "the code has never loaded, so it is
    almost certainly not saved or not republished" instead of a checklist.

    Never allowed to fail the request. The customer is trying to render a chat
    widget; a bookkeeping write must not be why their page has no chat on it.
    """
    now = datetime.now(UTC)
    seen = profile.widget_last_seen_at

    if seen is not None:
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=UTC)

        if now - seen < WIDGET_SEEN_INTERVAL:
            return

    try:
        profile.widget_last_seen_at = now
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Could not record a widget load for profile %s", profile.id
        )


@router.post(
    "/{widget_token}/conversations",
    response_model=ConversationOut,
    status_code=status.HTTP_201_CREATED,
)
def start_conversation(widget_token: str, db: Session = Depends(get_db)):
    profile = _profile(widget_token, db)

    service = ConversationService(db)
    # Both the organization and the profile. The organization is what makes the
    # engine answer out of the customer's catalog rather than the storefront's;
    # the profile is which of that customer's agents this widget *is*. A
    # workspace with both products has two, and passing only the organization is
    # what made a support widget open with "I'm Ada, the sales rep".
    conversation = service.start(profile.organization_id, profile.id)

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

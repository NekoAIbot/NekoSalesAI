"""Webhooks: Telegram and WhatsApp delivering a buyer's message.

Both routes do the same four things in the same order — verify, parse, answer,
acknowledge — and the order is load-bearing.

**Verify first, always.** A webhook must be reachable by the platform, which
means reachable by anyone who learns the URL. Unverified, a stranger could POST a
fabricated message and Nera would answer it as a real buyer, into a real
transcript, against a real approval queue. Both verifiers fail closed: an unset
secret rejects everything, because a deployment that skipped the secret is
exactly the one worth attacking.

**Then acknowledge almost everything.** Once a delivery is known to be genuine,
these routes return 200 even when handling it failed. That looks wrong and is
not: a non-2xx tells the platform to redeliver, and redelivering something that
crashed halfway means answering the buyer twice, or wedging the queue behind one
poisoned update while every other buyer waits. Failures are logged and the buyer
gets silence, which is recoverable. A retry storm is not.

Telegram is better served by ``app.messaging.poller``, which needs no public URL
at all. This route exists for a deployment that has one.
"""

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.config.logging import get_logger
from app.config.settings import settings
from app.database.session import get_db
from app.messaging.inbound import (
    parse_telegram_update,
    parse_whatsapp_payload,
    verify_telegram_secret,
    verify_whatsapp_signature,
)
from app.messaging.service import InboundMessagingService, storefront_organization_id

logger = get_logger(__name__)

router = APIRouter(
    prefix="/messaging",
    tags=["Messaging"],
)

# Returned for a delivery that was verified and then went wrong. See the module
# docstring: the platform must not be told to try again.
ACKNOWLEDGED = {"ok": True}


def _reject() -> Response:
    """One answer for a bad signature, a missing secret and a wrong secret.

    403 with no body. Telling a caller *which* of those it was is a hint about
    whether the endpoint is configured, and there is no legitimate caller who
    needs to know.
    """
    return Response(status_code=status.HTTP_403_FORBIDDEN)


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request, db: Session = Depends(get_db)):
    """One Telegram update."""
    if not verify_telegram_secret(
        request.headers.get("x-telegram-bot-api-secret-token"),
        settings.TELEGRAM_WEBHOOK_SECRET,
    ):
        logger.warning("Rejected a Telegram delivery with a bad secret token.")
        return _reject()

    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001 - a malformed body is not worth a retry
        logger.warning("Rejected a Telegram delivery with an unreadable body.")
        return ACKNOWLEDGED

    message = parse_telegram_update(payload)

    if message is None:
        # An edit, a group message, a join notification. Not an error.
        return ACKNOWLEDGED

    organization_id = storefront_organization_id(db)

    if organization_id is None:
        logger.error("No storefront organization; dropping a Telegram message.")
        return ACKNOWLEDGED

    service = InboundMessagingService(db)

    try:
        handled = service.handle(organization_id, message)
    except Exception:  # noqa: BLE001 - see the module docstring on retries
        db.rollback()
        logger.exception("Telegram delivery %s failed", message.delivery_id)
        return ACKNOWLEDGED

    service.deliver(message, handled.replies)

    return ACKNOWLEDGED


@router.get("/whatsapp/webhook", response_class=PlainTextResponse)
def whatsapp_verify(request: Request):
    """Meta's subscription handshake.

    Meta GETs the callback once with a challenge and expects it echoed back as
    bare text. Anything else — JSON, a quoted string, a 200 with a body it did
    not send — and the subscription is refused.
    """
    params = request.query_params

    if (
        params.get("hub.mode") == "subscribe"
        and settings.WHATSAPP_VERIFY_TOKEN
        and params.get("hub.verify_token") == settings.WHATSAPP_VERIFY_TOKEN
    ):
        return PlainTextResponse(params.get("hub.challenge", ""))

    logger.warning("Rejected a WhatsApp verification with a bad verify token.")

    return PlainTextResponse("", status_code=status.HTTP_403_FORBIDDEN)


@router.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    """A batch of WhatsApp messages.

    Meta batches: one POST can carry several messages from several people. It can
    also carry none — most deliveries in a busy account are ``statuses`` blocks
    reporting that an outbound message was delivered or read.
    """
    # The raw bytes, before parsing. The signature covers exactly what was sent,
    # so re-serialising the parsed JSON would change key order and whitespace and
    # fail every time.
    body = await request.body()

    if not verify_whatsapp_signature(
        request.headers.get("x-hub-signature-256"),
        body,
        settings.WHATSAPP_APP_SECRET,
    ):
        logger.warning("Rejected a WhatsApp delivery with a bad signature.")
        return _reject()

    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        logger.warning("Rejected a WhatsApp delivery with an unreadable body.")
        return ACKNOWLEDGED

    messages = parse_whatsapp_payload(payload)

    if not messages:
        return ACKNOWLEDGED

    organization_id = storefront_organization_id(db)

    if organization_id is None:
        logger.error("No storefront organization; dropping %d WhatsApp messages.",
                     len(messages))
        return ACKNOWLEDGED

    service = InboundMessagingService(db)

    for message in messages:
        # Per message, not per batch. One buyer's unanswerable question must not
        # cost the other four in the same delivery their replies.
        try:
            handled = service.handle(organization_id, message)
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.exception("WhatsApp delivery %s failed", message.delivery_id)
            continue

        service.deliver(message, handled.replies)

    return ACKNOWLEDGED

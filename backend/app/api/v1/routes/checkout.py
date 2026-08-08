"""Checkout and provisioning API.

Public, like the conversation routes — a buyer has no account until they have
paid, so requiring one to pay would be a circle.

The security boundary here is not authentication, it is that nothing a client
sends decides anything that matters. The amount comes from the catalog. Paid
status comes from Paystack, either through a signature-checked webhook or a
server-to-server verification. The order reference is a 24-hex-character random
string, so reading someone else's order status requires guessing it.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.config.logging import get_logger
from app.config.settings import settings
from app.dependencies.database import get_db
from app.followups.service import FollowUpService
from app.models.order import Order
from app.payments import PaymentsNotConfigured, PaystackClient, PaystackError
from app.payments.checkout import CheckoutError, CheckoutService
from app.payments.provisioning import ProvisioningService
from app.repositories.organization_repository import OrganizationRepository
from app.schemas.checkout import (
    CheckoutRequest,
    CheckoutStatusOut,
    OrderOut,
    WorkspaceOut,
)

logger = get_logger(__name__)

router = APIRouter(
    prefix="/checkout",
    tags=["Checkout"],
)


def _storefront_org_id(db: Session) -> int:
    org = OrganizationRepository(db).get_by_slug(settings.STOREFRONT_ORG_SLUG)

    if org is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Checkout is not configured yet.",
        )

    return org.id


def _load_order(reference: str, db: Session) -> Order:
    order = CheckoutService(db).get_by_reference(reference)

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found.",
        )

    return order


def _provision_if_paid(order: Order, db: Session) -> WorkspaceOut | None:
    """Stand up the workspace for a paid order, or report the existing one.

    Called from both the status poll and the webhook. Provisioning is
    idempotent, so calling it twice is safe and calling it from whichever
    request arrives first is correct.
    """
    if not order.is_paid:
        return None

    service = ProvisioningService(db)

    try:
        result = service.provision(order)
    except Exception:
        # Already logged with a traceback inside the service. The buyer's
        # money is safe and recorded; surfacing a 500 here would only tell
        # them their payment failed, which is not what happened.
        profile = service.get_for_order(order)
        return WorkspaceOut.from_model(profile) if profile else None

    _schedule_follow_ups(result.profile, order, db)

    return WorkspaceOut.from_model(
        result.profile,
        api_key=result.api_key,
        temporary_password=result.temporary_password,
    )


def _schedule_follow_ups(profile, order: Order, db: Session) -> None:
    """Put the post-sale calendar on the books.

    Deliberately cannot fail the request. The workspace is already live and
    the customer is looking at the confirmation screen; a scheduling problem
    is the seller's to fix and must not surface as an error on a successful
    purchase. Idempotent, so the repeated polls from the status page do not
    produce repeated calendars.
    """
    try:
        FollowUpService(db).schedule_for(profile, order)
    except Exception:
        logger.exception(
            "Could not schedule follow-ups for order %s",
            order.paystack_reference,
        )


@router.get("/config")
def checkout_config():
    """Whether this deployment can take a payment, and in which mode.

    The front end asks before showing a buy button, so an unconfigured
    deployment says so plainly instead of offering a button that fails.
    """
    return {
        "enabled": settings.payments_enabled,
        "live_mode": settings.paystack_is_live,
        "public_key": settings.PAYSTACK_PUBLIC_KEY,
    }


@router.post(
    "/orders",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
)
def create_order(payload: CheckoutRequest, db: Session = Depends(get_db)):
    service = CheckoutService(db)

    try:
        order = service.create_order(
            organization_id=_storefront_org_id(db),
            plan_code=payload.plan_code,
            buyer_email=str(payload.email),
            buyer_name=payload.name,
            buyer_company=payload.company,
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
        logger.warning("Paystack refused a checkout: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Our payment provider could not start this checkout. Try again.",
        ) from exc

    return OrderOut.from_model(order)


@router.get("/orders/{reference}", response_model=CheckoutStatusOut)
def order_status(reference: str, db: Session = Depends(get_db)):
    """Poll for payment and provisioning progress.

    Verifies with Paystack while the order is still pending, so a buyer who
    paid and came straight back is not left waiting on a webhook.
    """
    order = _load_order(reference, db)

    if not order.is_paid and settings.payments_enabled:
        confirmed = CheckoutService(db).confirm_by_reference(reference)
        if confirmed is not None:
            order = confirmed

    return CheckoutStatusOut(
        order=OrderOut.from_model(order),
        workspace=_provision_if_paid(order, db),
    )


@router.post("/webhook", include_in_schema=False)
async def paystack_webhook(request: Request, db: Session = Depends(get_db)):
    """Paystack's server-to-server notification.

    The signature is checked against the raw request body before the payload
    is trusted for anything. Without that check this endpoint would let anyone
    on the internet mark any order paid by POSTing JSON at it.

    Always answers 200 once the signature is valid. Paystack retries on any
    other status, and retrying will not fix an event we have no order for.
    """
    raw = await request.body()
    client = PaystackClient()

    if not client.verify_signature(raw, request.headers.get("x-paystack-signature")):
        logger.warning("Rejected a webhook with an invalid signature.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature.",
        )

    try:
        event = await request.json()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Body was not JSON.",
        )

    charge = client.charge_from_webhook(event)

    if charge is None:
        # Some other event type. Acknowledged so Paystack stops resending it.
        return Response(status_code=status.HTTP_200_OK)

    order = CheckoutService(db, client=client).confirm(charge)

    if order is not None:
        _provision_if_paid(order, db)

    return Response(status_code=status.HTTP_200_OK)

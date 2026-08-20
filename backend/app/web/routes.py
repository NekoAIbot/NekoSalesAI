"""Server-rendered web pages.

Separate from the ``/api/v1`` routers: these return HTML for humans, the API
returns JSON for the widget and the dashboard. Keeping them apart means the
API contract is not accidentally shaped by what a template happened to need.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.catalog import CAPABILITIES, COMPANY, FAQS, PLANS
from app.config.settings import settings
from app.dependencies.database import get_db
from app.pricing.complexity import (
    CHANNEL_ADD_MINOR,
    CHANNEL_NAMES,
    CHANNEL_WEB,
    MAX_WORKFLOW_STEPS,
    PRODUCT_NAMES,
    VOLUME_BANDS,
)
from app.repositories.organization_repository import OrganizationRepository

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["Web"])


def _builder_options() -> dict:
    """The choices the build-your-own form offers.

    Read from ``app.pricing.complexity`` rather than written into the template,
    for the same reason the plan cards are read from the catalog: a form that
    listed a channel the engine cannot price would take an order we would then
    have to refuse. Prices are deliberately absent — the form collects a
    requirement and the server returns the figure.
    """
    return {
        "products": [
            {"code": code, "name": name} for code, name in PRODUCT_NAMES.items()
        ],
        "channels": [
            {
                "code": code,
                "name": CHANNEL_NAMES[code],
                "included": CHANNEL_ADD_MINOR[code] == 0,
            }
            for code in CHANNEL_ADD_MINOR
        ],
        "volume_bands": [limit for limit, _ in VOLUME_BANDS],
        "default_channel": CHANNEL_WEB,
        "max_workflow_steps": MAX_WORKFLOW_STEPS,
    }


@router.get("/", response_class=HTMLResponse)
def landing(request: Request, db: Session = Depends(get_db)):
    """The landing page.

    Everything on it is rendered from the same catalog the agent quotes from,
    so the page and the chat can never disagree about the price.

    The builder section is rendered from the pricing engine's own dimensions
    for the same reason. Note that no price reaches this template: the fixed
    tiers carry theirs because they are published figures, while a built
    product is priced by ``POST /api/v1/pricing/quote`` on demand.
    """
    org = OrganizationRepository(db).get_by_slug(settings.STOREFRONT_ORG_SLUG)

    return templates.TemplateResponse(
        request,
        "landing.html",
        {
            "company": COMPANY,
            "plans": PLANS,
            "capabilities": CAPABILITIES,
            "faqs": FAQS,
            "chat_available": org is not None,
            "builder": _builder_options(),
        },
    )


@router.get("/desk", response_class=HTMLResponse)
def desk(request: Request):
    """The staff sales desk. Auth happens client-side against the API."""
    return templates.TemplateResponse(
        request,
        "desk.html",
        {"company": COMPANY},
    )


@router.get("/checkout/return", response_class=HTMLResponse)
def checkout_return(request: Request):
    """Where Paystack sends the buyer back to.

    Renders the shell only. Payment status and provisioning progress are
    polled from the API, because arriving here proves the buyer left the
    checkout page and nothing more — whether money moved is a question only
    the server can answer.
    """
    return templates.TemplateResponse(
        request,
        "checkout_return.html",
        {"company": COMPANY},
    )

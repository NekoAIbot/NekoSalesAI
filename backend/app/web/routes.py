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
from app.repositories.organization_repository import OrganizationRepository

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["Web"])


@router.get("/", response_class=HTMLResponse)
def landing(request: Request, db: Session = Depends(get_db)):
    """The landing page.

    Everything on it is rendered from the same catalog the agent quotes from,
    so the page and the chat can never disagree about the price.
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

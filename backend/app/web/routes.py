"""Server-rendered web pages."""

from pathlib import Path

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.catalog import CAPABILITIES, COMPANY, FAQS
from app.config.settings import settings
from app.dependencies.database import get_db
from app.pricing.complexity import (
    CHANNEL_ADD_MINOR,
    CHANNEL_NAMES,
    CHANNEL_WEB,
    CONVERSATION_PRICE_MINOR,
    INTEGRATION_ADD_MINOR,
    INTEGRATION_LABELS,
    LANGUAGES,
    LANGUAGE_ADD_MINOR,
    MAX_INTEGRATIONS,
    MAX_LANGUAGES,
    MAX_QUOTABLE_CONVERSATIONS,
    PRODUCT_NAMES,
    PRODUCT_ORDER,
    PRODUCT_DESCRIPTIONS,
)
from app.repositories.organization_repository import OrganizationRepository

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

def _number_format(value):
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return value

templates.env.filters["number_format"] = _number_format

router = APIRouter(tags=["Web"])


def _builder_options() -> dict:
    """The choices the build-your-own form offers."""
    # Only purchasable products in canonical order
    products = [
        {"code": code, "name": PRODUCT_NAMES[code], "description": PRODUCT_DESCRIPTIONS[code]}
        for code in PRODUCT_ORDER
    ]

    # Integration labels from canonical catalog
    integration_labels = [
        {"code": code, "name": name}
        for code, name in INTEGRATION_LABELS.items()
    ]

    # Language options from canonical catalog
    languages = [
        {"code": code, "name": name}
        for code, name in LANGUAGES.items()
    ]

    return {
        "products": products,
        "channels": [
            {
                "code": code,
                "name": CHANNEL_NAMES[code],
                "add_minor": CHANNEL_ADD_MINOR[code],
                "included": CHANNEL_ADD_MINOR[code] == 0,
            }
            for code in CHANNEL_ADD_MINOR
        ],
        "default_channel": CHANNEL_WEB,
        "volume_presets": [250, 500, 1000, 2500, 5000, 10000, 25000],
        "max_volume": MAX_QUOTABLE_CONVERSATIONS,
        "conversation_price_minor": CONVERSATION_PRICE_MINOR,
        "integration_price_minor": INTEGRATION_ADD_MINOR,
        "max_integrations": MAX_INTEGRATIONS,
        "integration_labels": integration_labels,
        "language_price_minor": LANGUAGE_ADD_MINOR,
        "max_languages": MAX_LANGUAGES,
        "languages": languages,
    }


def _build_context(request: Request, db: Session, extra: dict | None = None) -> dict:
    """Shared context every public page renders with."""
    org = OrganizationRepository(db).get_by_slug(settings.STOREFRONT_ORG_SLUG)
    ctx = {
        "request": request,
        "company": COMPANY,
        "capabilities": CAPABILITIES,
        "faqs": FAQS,
        "now": datetime.now(),
        "chat_available": org is not None,
        "builder": _builder_options(),
    }
    if extra:
        ctx.update(extra)
    return ctx


@router.get("/", response_class=HTMLResponse)
def landing(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request,
        "home.html",
        _build_context(request, db, {"page": "home"}),
    )


@router.get("/products", response_class=HTMLResponse)
def products(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request,
        "products.html",
        _build_context(request, db, {"page": "products"}),
    )


@router.get("/workforce", response_class=HTMLResponse)
def workforce(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request,
        "workforce.html",
        _build_context(request, db, {"page": "workforce"}),
    )


@router.get("/demo", response_class=HTMLResponse)
def demo(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request,
        "demo.html",
        _build_context(request, db, {"page": "demo"}),
    )


@router.get("/build", response_class=HTMLResponse)
def build(request: Request, db: Session = Depends(get_db)):
    try:
        ctx = _build_context(request, db, {"page": "build"})
        return templates.TemplateResponse(
            request,
            "build.html",
            ctx,
        )
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise


@router.get("/pricing", response_class=HTMLResponse)
def pricing(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request,
        "pricing.html",
        _build_context(request, db, {"page": "pricing"}),
    )


@router.get("/trust", response_class=HTMLResponse)
def trust(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request,
        "trust.html",
        _build_context(request, db, {"page": "trust"}),
    )


@router.get("/login", response_class=HTMLResponse)
def login(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request,
        "login.html",
        _build_context(request, db, {"page": "login"}),
    )


@router.get("/signup", response_class=HTMLResponse)
def signup(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request,
        "signup.html",
        _build_context(request, db, {"page": "signup"}),
    )


@router.get("/brand", response_class=HTMLResponse)
def brand(request: Request):
    return templates.TemplateResponse(
        request,
        "brand.html",
        {"request": request, "company": COMPANY},
    )


@router.get("/desk", response_class=HTMLResponse)
def desk(request: Request):
    """The staff sales desk. Auth happens client-side against the API."""
    return templates.TemplateResponse(
        request,
        "desk.html",
        {"request": request, "company": COMPANY},
    )


@router.get("/checkout/return", response_class=HTMLResponse)
def checkout_return(request: Request):
    """Where Paystack sends the buyer back to."""
    return templates.TemplateResponse(
        request,
        "checkout_return.html",
        {"request": request, "company": COMPANY},
    )


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    """Customer dashboard — requires authentication via client-side token."""
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"request": request, "company": COMPANY, "page": "dashboard"},
    )


@router.get("/verify-email", response_class=HTMLResponse)
def verify_email(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request,
        "verify_email.html",
        _build_context(request, db, {"page": "verify-email"}),
    )


@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request,
        "forgot_password.html",
        _build_context(request, db, {"page": "forgot-password"}),
    )


@router.get("/reset-password", response_class=HTMLResponse)
def reset_password(request: Request, token: str = "", db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request,
        "reset_password.html",
        _build_context(request, db, {"page": "reset-password", "token": token}),
    )


@router.get("/mfa-setup", response_class=HTMLResponse)
def mfa_setup(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request,
        "mfa_setup.html",
        _build_context(request, db, {"page": "mfa-setup"}),
    )

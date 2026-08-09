"""Configure a workspace's product — the factory's intake desk.

Every route here is authenticated and scoped to the caller's organization.
That scoping is the tenant boundary — a user must not be able to read or
rewrite another company's product config by guessing an organization id, so
the filter lives in the query rather than in a post-fetch check.

One deliberate asymmetry: there is no route for the storefront's own config.
NekoSalesAI's plans and verified claims live in ``app.catalog.products`` as
reviewable Python; a web form that could rewrite them would be a way to change
our prices without a diff.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.dependencies.database import get_db
from app.models.user import User
from app.products.intake import IntakeError, IntakeService
from app.schemas.intake import IntakeIn
from app.schemas.intake_out import ConfigOut

router = APIRouter(
    prefix="/product-config",
    tags=["Product Config"],
)


@router.get(
    "",
    response_model=ConfigOut,
)
def get_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Read the caller's product config — what their agent will actually say."""
    return ConfigOut.from_config(IntakeService(db).current_config(current_user.organization_id))


@router.put(
    "",
    response_model=ConfigOut,
)
def put_config(
    payload: IntakeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Replace the caller's product config wholesale."""
    service = IntakeService(db)
    try:
        saved = service.save(current_user.organization_id, payload.to_config())
    except IntakeError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return ConfigOut.from_config(saved)

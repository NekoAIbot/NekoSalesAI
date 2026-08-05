from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationResponse,
    OrganizationUpdate,
)
from app.services.organization_service import OrganizationService

router = APIRouter(
    prefix="/organizations",
    tags=["Organizations"],
)


@router.post(
    "/",
    response_model=OrganizationResponse,
    status_code=201,
)
def create_organization(
    organization: OrganizationCreate,
    db: Session = Depends(get_db),
):
    service = OrganizationService(db)

    existing = service.repository.get_by_slug(organization.slug)
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Organization slug already exists.",
        )

    return service.create(organization)


@router.get(
    "/",
    response_model=list[OrganizationResponse],
)
def list_organizations(
    db: Session = Depends(get_db),
):
    service = OrganizationService(db)
    return service.list()


@router.get(
    "/{organization_id}",
    response_model=OrganizationResponse,
)
def get_organization(
    organization_id: int,
    db: Session = Depends(get_db),
):
    service = OrganizationService(db)

    organization = service.get(organization_id)

    if organization is None:
        raise HTTPException(
            status_code=404,
            detail="Organization not found.",
        )

    return organization


@router.put(
    "/{organization_id}",
    response_model=OrganizationResponse,
)
def update_organization(
    organization_id: int,
    data: OrganizationUpdate,
    db: Session = Depends(get_db),
):
    service = OrganizationService(db)

    organization = service.update(
        organization_id,
        data,
    )

    if organization is None:
        raise HTTPException(
            status_code=404,
            detail="Organization not found.",
        )

    return organization


@router.delete(
    "/{organization_id}",
)
def delete_organization(
    organization_id: int,
    db: Session = Depends(get_db),
):
    service = OrganizationService(db)

    deleted = service.delete(organization_id)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Organization not found.",
        )

    return {
        "message": "Organization deleted successfully."
    }

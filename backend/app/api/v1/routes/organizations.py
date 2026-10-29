from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.models.user import User
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
    "/me",
    response_model=OrganizationResponse,
)
def get_my_organization(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve the current authenticated user's organization."""
    if not current_user.organization_id:
        raise HTTPException(
            status_code=404,
            detail="No organization associated with this account.",
        )
    service = OrganizationService(db)
    org = service.get(current_user.organization_id)
    if not org:
        raise HTTPException(
            status_code=404,
            detail="Organization not found.",
        )
    return org


@router.get(
    "/",
    response_model=list[OrganizationResponse],
)
def list_organizations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List organizations. Regular users only see their own organization."""
    service = OrganizationService(db)
    if current_user.is_admin:
        return service.list()
    if current_user.organization_id:
        org = service.get(current_user.organization_id)
        return [org] if org else []
    return []


@router.get(
    "/{organization_id}",
    response_model=OrganizationResponse,
)
def get_organization(
    organization_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get organization by ID with multi-tenant isolation."""
    if current_user.organization_id != organization_id and not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to access this organization.",
        )
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update organization with strict ownership validation."""
    if current_user.organization_id != organization_id and not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to modify this organization.",
        )
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete organization with ownership verification."""
    if current_user.organization_id != organization_id and not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to delete this organization.",
        )
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

@router.get("/workspace/profiles")
def list_workspace_profiles(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List workspace profiles for the current user's organization."""
    from app.models.workspace_profile import WorkspaceProfile
    profiles = (
        db.execute(
            select(WorkspaceProfile).where(
                WorkspaceProfile.organization_id == current_user.organization_id
            )
        ).scalars().all()
    )
    return [
        {
            "id": p.id,
            "role": p.role,
            "agent_name": p.agent_name,
            "status": p.status,
            "company_name": p.company_name,
            "widget_token": p.widget_token,
            "plan_code": p.plan_code,
            "greeting": p.greeting,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "ready_at": p.ready_at.isoformat() if p.ready_at else None,
        }
        for p in profiles
    ]

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies.database import get_db
from app.schemas.lead import (
    LeadCreate,
    LeadResponse,
    LeadUpdate,
)
from app.services.lead_service import LeadService

router = APIRouter(
    prefix="/leads",
    tags=["Leads"],
)


@router.post(
    "/",
    response_model=LeadResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_lead(
    payload: LeadCreate,
    db: Session = Depends(get_db),
):
    return LeadService(db).create(payload)


@router.get(
    "/",
    response_model=list[LeadResponse],
)
def list_leads(
    status: str | None = None,
    db: Session = Depends(get_db),
):
    return LeadService(db).list(status=status)


@router.get(
    "/{lead_id}",
    response_model=LeadResponse,
)
def get_lead(
    lead_id: int,
    db: Session = Depends(get_db),
):
    lead = LeadService(db).get(lead_id)

    if lead is None:
        raise HTTPException(
            status_code=404,
            detail="Lead not found.",
        )

    return lead


@router.put(
    "/{lead_id}",
    response_model=LeadResponse,
)
def update_lead(
    lead_id: int,
    payload: LeadUpdate,
    db: Session = Depends(get_db),
):
    lead = LeadService(db).update(
        lead_id,
        payload,
    )

    if lead is None:
        raise HTTPException(
            status_code=404,
            detail="Lead not found.",
        )

    return lead


@router.delete(
    "/{lead_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_lead(
    lead_id: int,
    db: Session = Depends(get_db),
):
    deleted = LeadService(db).delete(lead_id)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Lead not found.",
        )

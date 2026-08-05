from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies.database import get_db
from app.schemas.contact import (
    ContactCreate,
    ContactUpdate,
    ContactResponse,
)
from app.services.contact_service import ContactService

router = APIRouter(
    prefix="/contacts",
    tags=["Contacts"],
)


@router.post(
    "/",
    response_model=ContactResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_contact(
    payload: ContactCreate,
    db: Session = Depends(get_db),
):
    return ContactService(db).create(payload)


@router.get(
    "/",
    response_model=list[ContactResponse],
)
def list_contacts(
    db: Session = Depends(get_db),
):
    return ContactService(db).list()


@router.get(
    "/{contact_id}",
    response_model=ContactResponse,
)
def get_contact(
    contact_id: int,
    db: Session = Depends(get_db),
):
    contact = ContactService(db).get(contact_id)

    if contact is None:
        raise HTTPException(
            status_code=404,
            detail="Contact not found.",
        )

    return contact


@router.put(
    "/{contact_id}",
    response_model=ContactResponse,
)
def update_contact(
    contact_id: int,
    payload: ContactUpdate,
    db: Session = Depends(get_db),
):
    contact = ContactService(db).update(
        contact_id,
        payload,
    )

    if contact is None:
        raise HTTPException(
            status_code=404,
            detail="Contact not found.",
        )

    return contact


@router.delete(
    "/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_contact(
    contact_id: int,
    db: Session = Depends(get_db),
):
    deleted = ContactService(db).delete(contact_id)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Contact not found.",
        )

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies.database import get_db
from app.schemas.customer import (
    CustomerCreate,
    CustomerResponse,
    CustomerUpdate,
)
from app.services.customer_service import CustomerService

router = APIRouter(
    prefix="/customers",
    tags=["Customers"],
)


@router.post(
    "/",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_customer(
    payload: CustomerCreate,
    db: Session = Depends(get_db),
):
    return CustomerService(db).create(payload)


@router.get(
    "/",
    response_model=list[CustomerResponse],
)
def list_customers(
    db: Session = Depends(get_db),
):
    return CustomerService(db).list()


@router.get(
    "/{customer_id}",
    response_model=CustomerResponse,
)
def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
):
    customer = CustomerService(db).get(customer_id)

    if customer is None:
        raise HTTPException(
            status_code=404,
            detail="Customer not found.",
        )

    return customer


@router.put(
    "/{customer_id}",
    response_model=CustomerResponse,
)
def update_customer(
    customer_id: int,
    payload: CustomerUpdate,
    db: Session = Depends(get_db),
):
    customer = CustomerService(db).update(
        customer_id,
        payload,
    )

    if customer is None:
        raise HTTPException(
            status_code=404,
            detail="Customer not found.",
        )

    return customer


@router.delete(
    "/{customer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_customer(
    customer_id: int,
    db: Session = Depends(get_db),
):
    deleted = CustomerService(db).delete(customer_id)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Customer not found.",
        )

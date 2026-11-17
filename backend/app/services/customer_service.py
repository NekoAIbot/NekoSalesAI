from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.repositories.customer_repository import CustomerRepository
from app.schemas.customer import CustomerCreate, CustomerUpdate


class CustomerService:

    def __init__(self, db: Session):
        self.repository = CustomerRepository(db)

    def create(self, organization_id: int, data: CustomerCreate):
        dump = data.model_dump()
        dump["organization_id"] = organization_id
        customer = Customer(**dump)
        return self.repository.create(customer)

    def list(self, organization_id: int):
        return self.repository.get_all(organization_id)

    def get(self, organization_id: int, customer_id: int):
        return self.repository.get(organization_id, customer_id)

    def update(self, organization_id: int, customer_id: int, data: CustomerUpdate):
        customer = self.repository.get(organization_id, customer_id)

        if customer is None:
            return None

        for key, value in data.model_dump(exclude_unset=True).items():
            if key != "organization_id":
                setattr(customer, key, value)

        return self.repository.update(customer)

    def delete(self, organization_id: int, customer_id: int):
        customer = self.repository.get(organization_id, customer_id)

        if customer is None:
            return False

        self.repository.delete(customer)
        return True

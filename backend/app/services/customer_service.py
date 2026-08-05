from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.repositories.customer_repository import CustomerRepository
from app.schemas.customer import CustomerCreate, CustomerUpdate


class CustomerService:

    def __init__(self, db: Session):
        self.repository = CustomerRepository(db)

    def create(self, data: CustomerCreate):
        customer = Customer(**data.model_dump())
        return self.repository.create(customer)

    def list(self):
        return self.repository.get_all()

    def get(self, customer_id: int):
        return self.repository.get(customer_id)

    def update(self, customer_id: int, data: CustomerUpdate):
        customer = self.repository.get(customer_id)

        if customer is None:
            return None

        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(customer, key, value)

        return self.repository.update(customer)

    def delete(self, customer_id: int):
        customer = self.repository.get(customer_id)

        if customer is None:
            return False

        self.repository.delete(customer)
        return True

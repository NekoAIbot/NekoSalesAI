from sqlalchemy.orm import Session

from app.models.customer import Customer


class CustomerRepository:

    def __init__(self, db: Session):
        self.db = db

    def create(self, customer: Customer):
        self.db.add(customer)
        self.db.commit()
        self.db.refresh(customer)
        return customer

    def get(self, organization_id: int, customer_id: int):
        return (
            self.db.query(Customer)
            .filter(Customer.id == customer_id, Customer.organization_id == organization_id)
            .first()
        )

    def get_all(self, organization_id: int):
        return (
            self.db.query(Customer)
            .filter(Customer.organization_id == organization_id)
            .order_by(Customer.first_name)
            .all()
        )

    def update(self, customer: Customer):
        self.db.commit()
        self.db.refresh(customer)
        return customer

    def delete(self, customer: Customer):
        self.db.delete(customer)
        self.db.commit()

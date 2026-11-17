from sqlalchemy.orm import Session

from app.models.contact import Contact
from app.models.customer import Customer


class ContactRepository:

    def __init__(self, db: Session):
        self.db = db

    def create(self, contact: Contact):
        self.db.add(contact)
        self.db.commit()
        self.db.refresh(contact)
        return contact

    def get(self, organization_id: int, contact_id: int):
        return (
            self.db.query(Contact)
            .join(Customer, Contact.customer_id == Customer.id)
            .filter(Contact.id == contact_id, Customer.organization_id == organization_id)
            .first()
        )

    def get_all(self, organization_id: int):
        return (
            self.db.query(Contact)
            .join(Customer, Contact.customer_id == Customer.id)
            .filter(Customer.organization_id == organization_id)
            .order_by(Contact.first_name)
            .all()
        )

    def update(self, contact: Contact):
        self.db.commit()
        self.db.refresh(contact)
        return contact

    def delete(self, contact: Contact):
        self.db.delete(contact)
        self.db.commit()

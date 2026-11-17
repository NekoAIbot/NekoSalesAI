from sqlalchemy.orm import Session

from app.models.contact import Contact
from app.models.customer import Customer
from app.repositories.contact_repository import ContactRepository
from app.schemas.contact import ContactCreate, ContactUpdate


class ContactService:

    def __init__(self, db: Session):
        self.db = db
        self.repository = ContactRepository(db)

    def create(self, organization_id: int, data: ContactCreate):
        customer = (
            self.db.query(Customer)
            .filter(Customer.id == data.customer_id, Customer.organization_id == organization_id)
            .first()
        )
        if not customer:
            return None
        contact = Contact(**data.model_dump())
        return self.repository.create(contact)

    def list(self, organization_id: int):
        return self.repository.get_all(organization_id)

    def get(self, organization_id: int, contact_id: int):
        return self.repository.get(organization_id, contact_id)

    def update(self, organization_id: int, contact_id: int, data: ContactUpdate):
        contact = self.repository.get(organization_id, contact_id)

        if contact is None:
            return None

        for key, value in data.model_dump(exclude_unset=True).items():
            if key != "customer_id":
                setattr(contact, key, value)

        return self.repository.update(contact)

    def delete(self, organization_id: int, contact_id: int):
        contact = self.repository.get(organization_id, contact_id)

        if contact is None:
            return False

        self.repository.delete(contact)
        return True

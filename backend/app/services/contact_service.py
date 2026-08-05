from sqlalchemy.orm import Session

from app.models.contact import Contact
from app.repositories.contact_repository import ContactRepository
from app.schemas.contact import ContactCreate, ContactUpdate


class ContactService:

    def __init__(self, db: Session):
        self.repository = ContactRepository(db)

    def create(self, data: ContactCreate):
        contact = Contact(**data.model_dump())
        return self.repository.create(contact)

    def list(self):
        return self.repository.get_all()

    def get(self, contact_id: int):
        return self.repository.get(contact_id)

    def update(self, contact_id: int, data: ContactUpdate):
        contact = self.repository.get(contact_id)

        if contact is None:
            return None

        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(contact, key, value)

        return self.repository.update(contact)

    def delete(self, contact_id: int):
        contact = self.repository.get(contact_id)

        if contact is None:
            return False

        self.repository.delete(contact)
        return True

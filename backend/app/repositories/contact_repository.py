from sqlalchemy.orm import Session

from app.models.contact import Contact


class ContactRepository:

    def __init__(self, db: Session):
        self.db = db

    def create(self, contact: Contact):
        self.db.add(contact)
        self.db.commit()
        self.db.refresh(contact)
        return contact

    def get(self, contact_id: int):
        return (
            self.db.query(Contact)
            .filter(Contact.id == contact_id)
            .first()
        )

    def get_all(self):
        return (
            self.db.query(Contact)
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

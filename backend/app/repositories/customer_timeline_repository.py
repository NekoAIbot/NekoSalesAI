from sqlalchemy.orm import Session

from app.models.customer_timeline import CustomerTimeline


class CustomerTimelineRepository:

    def __init__(self, db: Session):
        self.db = db

    def create(self, **kwargs):
        item = CustomerTimeline(**kwargs)

        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)

        return item

    def by_customer(self, customer_id: int):
        return (
            self.db.query(CustomerTimeline)
            .filter(
                CustomerTimeline.customer_id == customer_id
            )
            .order_by(
                CustomerTimeline.created_at.desc()
            )
            .all()
        )


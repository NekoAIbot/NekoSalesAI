from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.ai.scheduler.worker import SchedulerWorker


class SchedulerService:

    def __init__(self, db: Session):
        self.db = db
        self.worker = SchedulerWorker(db)

    def run_cycle(self):

        customers = self.db.query(Customer).all()

        for customer in customers:
            self.worker.process_customer(customer.id)


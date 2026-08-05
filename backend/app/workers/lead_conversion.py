from app.models.lead import Lead
from app.models.customer import Customer

from app.core.events import event_bus
from app.core.events.events import CUSTOMER_CREATED


class LeadConversionWorker:


    def __init__(self, db):
        self.db = db


    def run(self, payload):

        lead_id = payload.get("lead_id")


        lead = (
            self.db.query(Lead)
            .filter(Lead.id == lead_id)
            .first()
        )


        if not lead:
            print("Lead not found")
            return False


        customer = Customer(
            organization_id=lead.organization_id,
            first_name=lead.first_name,
            last_name=lead.last_name,
            email=lead.email,
            phone=lead.phone,
            company=lead.company,
            job_title=lead.job_title,
            notes=lead.notes,
        )


        self.db.add(customer)

        self.db.flush()


        lead.status = "Converted"


        self.db.commit()


        print(
            f"Lead converted to customer: {customer.id}"
        )


        event_bus.publish(
            CUSTOMER_CREATED,
            {
                "customer_id": customer.id,
                "name": f"{customer.first_name} {customer.last_name}",
                "email": customer.email,
                "phone": customer.phone,
                "company": customer.company,
                "job_title": customer.job_title,
                "source": lead.source,
                "notes": customer.notes,
            }
        )


        return True

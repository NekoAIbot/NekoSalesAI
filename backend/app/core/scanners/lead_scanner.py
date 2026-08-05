from sqlalchemy.orm import Session

from app.models.lead import Lead
from app.core.workers import dispatcher


class LeadScanner:


    def __init__(self, db: Session):
        self.db = db


    def scan(self):

        print("\n========== LEAD SCANNER ==========")


        leads = (
            self.db.query(Lead)
            .filter(Lead.status == "New")
            .all()
        )


        if not leads:
            print("No new leads found.")
            print("==================================\n")
            return


        for lead in leads:

            print(
                f"Processing lead: {lead.first_name} {lead.last_name}"
            )


            dispatcher.assign(
                "lead_conversion",
                {
                    "lead_id": lead.id
                }
            )


        print("==================================\n")

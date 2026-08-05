import time

from app.database.database import SessionLocal
from app.models.lead import Lead

from app.core.events import event_bus
from app.core.events.events import CUSTOMER_CREATED

from app.core.workers import register_workers
from app.core.scheduler import heartbeat

from app.core.scanners.lead_scanner import LeadScanner


register_workers()

heartbeat.start()


db = SessionLocal()


lead = Lead(
    organization_id=1,
    first_name="John",
    last_name="Smith",
    email="john@example.com",
    company="Smith Digital",
    job_title="CEO",
    source="AI Scanner",
    status="New",
)


db.add(lead)
db.commit()


print("Created lead:", lead.id)


LeadScanner(db).scan()


time.sleep(20)


db.close()

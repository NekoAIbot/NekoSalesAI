from app.database.database import SessionLocal

from app.core.scanners.customer_scanner import CustomerScanner
from app.core.scanners.lead_scanner import LeadScanner


class ScannerManager:


    def run(self):

        db = SessionLocal()

        try:

            LeadScanner(db).scan()

            CustomerScanner(db).scan()


        finally:

            db.close()


scanner = ScannerManager()

import json

from app.database.database import SessionLocal
from app.models.customer import Customer
from app.core.ai.memory_engine import memory_engine


class ProfileBuilder:

    def build(self, customer_id):

        db = SessionLocal()

        customer = db.query(Customer).filter(
            Customer.id == customer_id
        ).first()

        if customer is None:
            db.close()
            return None

        memories = memory_engine.recall(customer_id)

        profile = {
            "company": customer.company,
            "job_title": customer.job_title,
            "stage": customer.lifecycle_stage,
            "intent": customer.buying_intent,
            "risk": customer.risk_level,
            "engagement": customer.engagement_score,
            "opportunity": customer.opportunity_score,
            "memory_count": len(memories),
        }

        customer.ai_profile = json.dumps(profile)

        db.commit()
        db.close()

        return profile


profile_builder = ProfileBuilder()

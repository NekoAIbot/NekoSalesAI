from app.database.database import SessionLocal
from app.models.customer import Customer

from app.core.ai.deal_stage import deal_stage
from app.core.ai.risk_engine import risk_engine
from app.core.ai.profile_builder import profile_builder


class ConversationProcessor:

    def process(self, customer_id, message):


        db = SessionLocal()

        customer = (
            db.query(Customer)
            .filter(Customer.id == customer_id)
            .first()
        )

        if customer is None:
            db.close()
            return None

        customer.lifecycle_stage = deal_stage.update(customer)
        customer.risk_level = risk_engine.calculate(customer)

        db.commit()
        db.close()

        profile_builder.build(customer_id)

        return True


conversation_processor = ConversationProcessor()

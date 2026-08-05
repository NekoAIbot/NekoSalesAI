from app.ai.orchestrator.conversation_orchestrator import ConversationOrchestrator

from app.models.timeline_event import TimelineEvent
from app.models.ai_memory import AIMemory
from app.models.customer import Customer

from app.database.database import SessionLocal

from app.core.workers.dispatcher import dispatcher

from app.core.ai.conversation_processor import conversation_processor
from app.core.ai.customer_learning import customer_learning
from app.core.ai.decision_engine import decision_engine
from app.core.ai.action_router import action_router
from app.core.ai.deal_probability import deal_probability
from app.core.ai.customer_health import customer_health
from app.core.ai.recommendation_engine import recommendation_engine


class ConversationAgent:

    def __init__(self, db):
        self.db = db
        self.orchestrator = ConversationOrchestrator(db)

    def generate_message(self, decision):

        action = decision.get("action", "NONE")

        if action == "FOLLOW_UP":
            return (
                "I noticed your interest and wanted to follow up. "
                "I'd be happy to help you find the best solution."
            )

        if action == "HANDOFF":
            return (
                "I'll connect you with a specialist who can assist you further."
            )

        if action == "CREATE_TASK":
            return (
                "I've noted your request and our team will follow up shortly."
            )

        return (
            "Hello, thanks for your interest. "
            "I'd love to learn more about what you're looking for and see how we can help."
        )

    def run(self, payload):

        print("\n========== CONVERSATION AGENT ==========")

        db = SessionLocal()

        try:

            customer_id = payload["customer_id"]

            incoming_message = payload.get(
                "message",
                "Customer started a conversation."
            )

            analysis = self.orchestrator.process(
                customer_id,
                incoming_message,
            )

            decision = analysis["decision"]

            conversation_processor.process(
                customer_id,
                incoming_message,
            )

            learning = customer_learning.learn(
                customer_id,
                incoming_message,
            )

            customer = (
                db.query(Customer)
                .filter(Customer.id == customer_id)
                .first()
            )

            probability = deal_probability.predict(customer)
            health = customer_health.evaluate(customer)
            recommendations = recommendation_engine.recommend(customer)

            message = self.generate_message(decision)

            db.add(
                TimelineEvent(
                    organization_id=1,
                    customer_id=customer_id,
                    event_type="AI_MESSAGE",
                    title="AI Generated Customer Message",
                    description=message,
                    actor="Conversation Agent",
                    source="AI",
                )
            )

            db.add(
                AIMemory(
                    organization_id=1,
                    customer_id=customer_id,
                    memory_type="conversation",
                    importance=7,
                    content=message,
                )
            )

            dispatcher.assign(
                worker="customer_intelligence",
                payload={
                    "customer_id": customer_id,
                    "trigger": "Conversation",
                    "reason": "Customer Activity",
                    "message": message,
                },
                priority="MEDIUM",
            )

            db.commit()

            print("\n========== SALES AI ==========")

            if learning:
                print(f"Lifecycle Stage : {learning['stage']}")
                print(f"Buying Intent   : {learning['intent']}")
                print(f"Opportunity     : {learning['score']}")
                print(f"Risk Level      : {learning['risk']}")
                print(f"Next Action     : {learning['action']}")

                business_decision = decision_engine.decide(learning)

                print("\nAI BUSINESS DECISION:")
                print(business_decision)

                action_result = action_router.execute(
                    business_decision,
                    customer.id
                )

                print("\nACTION ROUTER RESULT:")
                print(action_result)

                if action_result.get("executed"):
                    dispatcher.assign(
                        worker=action_result["action"],
                        payload=action_result,
                        priority=business_decision.get("priority", "MEDIUM")
                    )

            print(f"Engagement      : {customer.engagement_score}")
            print(f"Deal Chance     : {probability}%")
            print(f"Customer Health : {health}")

            print("Recommendations :")
            for item in recommendations:
                print(f" - {item}")

            print("========================================")

            print("\nGenerated Message:")
            print(message)
            print("Conversation saved.")
            print("Customer Intelligence queued.")
            print("========================================\n")

            return analysis

        finally:
            db.close()

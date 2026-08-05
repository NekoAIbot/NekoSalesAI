from app.core.ai.memory_engine import memory_engine


class CustomerLearningEngine:

    def analyze_intent(self, message):

        text = message.lower()

        if any(word in text for word in [
            "price",
            "cost",
            "pricing",
            "how much",
            "buy",
            "purchase"
        ]):
            return "BUYING"

        if any(word in text for word in [
            "interested",
            "tell me more",
            "details",
            "information",
            "learn"
        ]):
            return "INTERESTED"

        if any(word in text for word in [
            "problem",
            "issue",
            "not working",
            "cancel",
            "refund"
        ]):
            return "RISK"

        return "GENERAL"


    def calculate_stage(self, intent, memories):

        if intent == "BUYING":
            return "HOT_PROSPECT"

        if intent == "INTERESTED":
            return "ENGAGED"

        if len(memories) > 5:
            return "NURTURING"

        return "NEW_LEAD"


    def calculate_risk(self, intent):

        if intent == "RISK":
            return "HIGH"

        return "LOW"


    def learn(self, customer_id, message):

        print("\n========== CUSTOMER LEARNING ==========")

        print(f"Customer : {customer_id}")
        print(f"Message  : {message}")


        memory_engine.remember(
            customer_id=customer_id,
            category="conversation",
            content={
                "message": message
            }
        )


        memories = memory_engine.recall(customer_id)


        intent = self.analyze_intent(message)


        learning = {

            "stage": self.calculate_stage(
                intent,
                memories
            ),

            "intent": intent,

            "score": len(memories),

            "risk": self.calculate_risk(intent),

            "action":
                "FOLLOW_UP"
                if intent != "GENERAL"
                else "CONTINUE_CONVERSATION",

            "memories": memories

        }


        print("Learning complete.")
        print("======================================")


        return learning



customer_learning = CustomerLearningEngine()

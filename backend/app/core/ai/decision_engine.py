class DecisionEngine:

    def decide(self, learning):

        intent = learning.get("intent")
        risk = learning.get("risk")

        if risk == "HIGH":
            return {
                "action": "ESCALATE",
                "priority": "HIGH",
                "reason": "Customer risk detected",
                "notify_owner": True
            }


        if intent == "BUYING":
            return {
                "action": "SALES_FOLLOW_UP",
                "priority": "HIGH",
                "reason": "Buying intent detected",
                "notify_owner": True
            }


        if intent == "INTERESTED":
            return {
                "action": "NURTURE",
                "priority": "MEDIUM",
                "reason": "Customer showing interest",
                "notify_owner": False
            }


        return {
            "action": "CONTINUE_CONVERSATION",
            "priority": "LOW",
            "reason": "No strong signal detected",
            "notify_owner": False
        }


decision_engine = DecisionEngine()

class ActionRouter:

    def execute(self, decision, customer_id):

        action = decision.get("action")

        if action == "SALES_FOLLOW_UP":
            return {
                "executed": True,
                "action": "CREATE_SALES_TASK",
                "customer_id": customer_id,
                "message": "High intent customer requires follow up"
            }


        if action == "NURTURE":
            return {
                "executed": True,
                "action": "START_NURTURE_SEQUENCE",
                "customer_id": customer_id,
                "message": "Customer added to nurture flow"
            }


        if action == "ESCALATE":
            return {
                "executed": True,
                "action": "OWNER_ALERT",
                "customer_id": customer_id,
                "message": "Customer risk requires human attention"
            }


        return {
            "executed": False,
            "action": "NONE",
            "customer_id": customer_id
        }


action_router = ActionRouter()

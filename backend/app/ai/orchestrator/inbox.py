class AIInbox:

    def receive(
        self,
        customer_id,
        message,
    ):

        return {
            "customer_id": customer_id,
            "message": message,
        }


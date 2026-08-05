from app.core.workers.execution_manager import execution_manager


class WorkflowOrchestrator:

    def start(self, workflow_name, payload):

        print("\n========== WORKFLOW ==========")
        print(f"Workflow : {workflow_name}")

        if workflow_name == "CUSTOMER_ONBOARDING":
            return self.customer_onboarding(payload)

        if workflow_name == "SALES_PIPELINE":
            return self.sales_pipeline(payload)

        raise ValueError(f"Unknown workflow: {workflow_name}")

    def customer_onboarding(self, payload):

        customer_id = payload["customer_id"]

        execution_manager.execute(
            "START_CONVERSATION",
            {
                "customer_id": customer_id
            }
        )

        execution_manager.execute(
            "CUSTOMER_INTELLIGENCE",
            {
                "customer_id": customer_id
            }
        )

        return {
            "workflow": "CUSTOMER_ONBOARDING",
            "success": True
        }

    def sales_pipeline(self, payload):

        customer_id = payload["customer_id"]

        execution_manager.execute(
            "CREATE_SALES_TASK",
            {
                "customer_id": customer_id,
                "action": "CREATE_SALES_TASK",
                "message": "Workflow generated sales follow-up"
            },
            priority="HIGH",
        )

        return {
            "workflow": "SALES_PIPELINE",
            "success": True
        }


workflow_orchestrator = WorkflowOrchestrator()

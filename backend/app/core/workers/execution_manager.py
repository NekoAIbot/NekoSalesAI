import time

from app.core.workers.worker_registry import worker_registry
from app.core.workers.execution_context import ExecutionContext
from app.core.workers.execution_logger import execution_logger
from app.core.workers.dead_letter_queue import dead_letter_queue


class ExecutionManager:

    def execute(
        self,
        worker_name,
        payload,
        priority="MEDIUM",
    ):

        context = ExecutionContext(
            worker_name=worker_name,
            customer_id=payload.get("customer_id"),
            priority=priority,
            payload=payload,
        )

        execution_id = execution_logger.create(context)

        start_time = time.time()

        print("\n========== EXECUTION MANAGER ==========")
        print(f"Execution ID : {context.execution_id}")
        print(f"Database ID  : {execution_id}")
        print(f"Worker       : {worker_name}")
        print(f"Customer     : {context.customer_id}")
        print(f"Priority     : {priority}")

        result = None
        last_error = None
        success = False


        while context.retry_count <= context.max_retries:

            attempt = context.retry_count + 1

            print(
                f"\nAttempt {attempt}/"
                f"{context.max_retries + 1}"
            )

            try:

                result = worker_registry.execute(
                    worker_name,
                    payload,
                )

                success = True
                break


            except Exception as exc:

                last_error = exc

                if context.retry_count >= context.max_retries:
                    break

                context.retry_count += 1

                print(
                    f"[RETRY] "
                    f"{context.retry_count}/{context.max_retries}"
                )


        duration_ms = int(
            (time.time() - start_time) * 1000
        )


        execution_logger.complete(
            execution_id,
            success,
            result=result,
            error=str(last_error) if last_error else None,
            duration_ms=duration_ms,
            retry_count=context.retry_count,
        )


        if not success:

            dead_letter_queue.push(
                worker_name,
                payload,
                last_error,
            )


            print("\nExecution FAILED → DLQ")
            print("======================================")

            return {
                "context": context,
                "success": False,
                "error": str(last_error),
                "dead_letter": True,
            }


        print("\nExecution SUCCESS")
        print("======================================")

        return {
            "context": context,
            "success": True,
            "result": result,
        }


execution_manager = ExecutionManager()

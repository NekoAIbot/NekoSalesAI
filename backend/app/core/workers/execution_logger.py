import json
from datetime import datetime

from app.database.database import SessionLocal
from app.models.worker_execution import WorkerExecution


class ExecutionLogger:

    def create(self, context):

        db = SessionLocal()

        execution = WorkerExecution(
            worker_name=context.worker_name,
            customer_id=context.customer_id,
            success=False,
            started_at=context.started_at,
            finished_at=context.started_at,
            duration_ms=0,
            payload_json=json.dumps(context.payload),
            status="RUNNING",
            retry_count=context.retry_count,
            max_retries=context.max_retries,
        )

        db.add(execution)
        db.commit()
        db.refresh(execution)

        db.close()

        return execution.id


    def complete(
        self,
        execution_id,
        success,
        result=None,
        error=None,
        duration_ms=0,
        retry_count=0,
    ):

        db = SessionLocal()

        execution = (
            db.query(WorkerExecution)
            .filter(
                WorkerExecution.id == execution_id
            )
            .first()
        )

        if execution:

            execution.success = success
            execution.finished_at = datetime.utcnow()
            execution.duration_ms = duration_ms
            execution.retry_count = retry_count

            execution.status = (
                "SUCCESS"
                if success
                else "FAILED"
            )

            if result:
                execution.result_json = json.dumps(result)

            if error:
                execution.error_message = error

            db.commit()

        db.close()


execution_logger = ExecutionLogger()

import json
import traceback
from abc import ABC, abstractmethod
from datetime import datetime

from app.database.database import SessionLocal
from app.models.worker_execution import WorkerExecution


class BaseWorker(ABC):

    worker_name = "BASE_WORKER"

    def run(self, payload):

        db = SessionLocal()

        started_at = datetime.utcnow()

        execution = WorkerExecution(
            worker_name=self.worker_name,
            customer_id=payload.get("customer_id"),
            success=False,
            started_at=started_at,
            finished_at=started_at,
            duration_ms=0,
            payload_json=json.dumps(payload),
        )

        db.add(execution)
        db.commit()

        try:

            data = self.execute(payload)

            finished_at = datetime.utcnow()

            execution.success = True
            execution.finished_at = finished_at
            execution.duration_ms = int(
                (finished_at - started_at).total_seconds() * 1000
            )
            execution.result_json = json.dumps(data)

            db.commit()

            return {
                "success": True,
                "worker": self.worker_name,
                "execution_id": execution.id,
                "customer_id": payload.get("customer_id"),
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
                "duration_ms": execution.duration_ms,
                "message": "Completed successfully",
                "data": data,
            }

        except Exception as exc:

            finished_at = datetime.utcnow()

            execution.success = False
            execution.finished_at = finished_at
            execution.duration_ms = int(
                (finished_at - started_at).total_seconds() * 1000
            )
            execution.error_message = str(exc)
            execution.result_json = traceback.format_exc()

            db.commit()

            return {
                "success": False,
                "worker": self.worker_name,
                "execution_id": execution.id,
                "customer_id": payload.get("customer_id"),
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
                "duration_ms": execution.duration_ms,
                "error": str(exc),
            }

        finally:
            db.close()

    @abstractmethod
    def execute(self, payload):
        pass

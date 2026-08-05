import json

from app.database.database import SessionLocal
from app.models.dead_letter_job import DeadLetterJob


class DeadLetterQueue:

    def push(
        self,
        worker_name,
        payload,
        error,
    ):

        db = SessionLocal()

        job = DeadLetterJob(
            worker_name=worker_name,
            customer_id=payload.get("customer_id"),
            payload_json=json.dumps(payload),
            error_message=str(error),
            status="FAILED",
        )

        db.add(job)
        db.commit()
        db.refresh(job)

        db.close()

        print("\n========== DEAD LETTER QUEUE ==========")
        print(f"DLQ ID   : {job.id}")
        print(f"Worker   : {worker_name}")
        print(f"Reason   : {error}")
        print("======================================")

        return job.id


    def list_failed(self):

        db = SessionLocal()

        jobs = (
            db.query(DeadLetterJob)
            .filter(
                DeadLetterJob.status == "FAILED"
            )
            .all()
        )

        db.close()

        return jobs


dead_letter_queue = DeadLetterQueue()

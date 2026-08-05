import json

from app.database.database import SessionLocal
from app.models.dead_letter_job import DeadLetterJob

from app.core.workers.execution_manager import execution_manager


class DLQReplayEngine:


    def replay(self, job_id):

        db = SessionLocal()

        job = (
            db.query(DeadLetterJob)
            .filter(
                DeadLetterJob.id == job_id
            )
            .first()
        )

        if not job:
            db.close()
            print("DLQ job not found")
            return False


        print("\n========== DLQ REPLAY ==========")

        payload = json.loads(
            job.payload_json
        )


        result = execution_manager.execute(
            job.worker_name,
            payload,
        )


        if result.get("success"):

            job.status = "RECOVERED"

            print(
                f"DLQ Job {job.id} recovered"
            )

        else:

            job.status = "FAILED"

            print(
                f"DLQ Job {job.id} still failing"
            )


        db.commit()
        db.close()


        print("================================")

        return result



dlq_replay_engine = DLQReplayEngine()

from app.core.workers.dispatcher import dispatcher

from app.database.database import SessionLocal

from app.workers.lead_conversion import LeadConversionWorker
from app.workers.customer_onboarding import CustomerOnboardingWorker

from app.core.workers.conversation_agent import ConversationAgent
from app.core.workers.customer_intelligence import CustomerIntelligenceWorker
from app.core.workers.customer_review import CustomerReviewWorker
from app.core.workers.customer_success import CustomerSuccessWorker


class WorkerRuntime:

    def process_next(self):

        job = dispatcher.next_job()

        if job is None:
            return

        worker_name = job["worker"]
        payload = job["payload"]

        print("\n========== AI WORKER ==========")
        print("Worker   :", worker_name)
        print("Priority :", job.get("priority", "MEDIUM"))
        print("Created  :", job.get("created_at"))
        print("Payload  :", payload)

        db = SessionLocal()

        try:

            if worker_name == "lead_conversion":
                worker = LeadConversionWorker(db)

            elif worker_name == "customer_onboarding":
                worker = CustomerOnboardingWorker(db)

            elif worker_name == "conversation_agent":
                worker = ConversationAgent(db)

            elif worker_name == "customer_intelligence":
                worker = CustomerIntelligenceWorker(db)

            elif worker_name == "customer_review":
                worker = CustomerReviewWorker(db)

            elif worker_name == "customer_success":
                worker = CustomerSuccessWorker(db)

            else:
                print("Unknown worker:", worker_name)
                return


            result = worker.run(payload)

            print("Result :", result)
            print("Status : COMPLETED")


        except Exception as e:

            print("Status : FAILED")
            print("Error :", e)


        finally:
            db.close()


        print("================================")


runtime = WorkerRuntime()

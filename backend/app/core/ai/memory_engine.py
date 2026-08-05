import json

from app.database.database import SessionLocal
from app.models.ai_memory import AIMemory


class MemoryEngine:

    def remember(self, customer_id, category, content):

        db = SessionLocal()

        db.add(
            AIMemory(
                organization_id=1,
                customer_id=customer_id,
                memory_type=category,
                importance=5,
                content=json.dumps(content),
            )
        )

        db.commit()
        db.close()


    def recall(self, customer_id):

        db = SessionLocal()

        memories = (
            db.query(AIMemory)
            .filter(
                AIMemory.customer_id == customer_id
            )
            .order_by(
                AIMemory.id.desc()
            )
            .limit(20)
            .all()
        )


        result = []

        for memory in memories:

            result.append(
                {
                    "id": memory.id,
                    "type": memory.memory_type,
                    "importance": memory.importance,
                    "content": json.loads(memory.content)
                }
            )


        db.close()

        return result


memory_engine = MemoryEngine()

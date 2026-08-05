from datetime import datetime
from pydantic import BaseModel, ConfigDict


class AIMemoryCreate(BaseModel):

    organization_id: int
    customer_id: int | None = None

    memory_type: str

    importance: int = 5

    content: str


class AIMemoryResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    customer_id: int | None

    memory_type: str
    importance: int

    content: str

    created_at: datetime

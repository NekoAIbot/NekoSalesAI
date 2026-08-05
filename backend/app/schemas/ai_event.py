from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AIEventCreate(BaseModel):

    organization_id: int
    customer_id: int | None = None

    event_type: str
    source: str

    payload: str


class AIEventResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: int

    organization_id: int
    customer_id: int | None

    event_type: str
    source: str
    payload: str

    status: str

    created_at: datetime
    processed_at: datetime | None

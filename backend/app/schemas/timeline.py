from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TimelineCreate(BaseModel):

    organization_id: int
    customer_id: int | None = None

    event_type: str

    title: str

    description: str | None = None

    actor: str = "System"

    source: str = "AI"


class TimelineResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: int

    organization_id: int

    customer_id: int | None

    event_type: str

    title: str

    description: str | None

    actor: str

    source: str

    created_at: datetime

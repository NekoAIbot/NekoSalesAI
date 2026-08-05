from pydantic import BaseModel, ConfigDict, EmailStr


class LeadBase(BaseModel):
    organization_id: int
    first_name: str
    last_name: str
    email: EmailStr | None = None
    phone: str | None = None
    company: str | None = None
    job_title: str | None = None
    source: str = "Manual"
    status: str = "New"
    notes: str | None = None


class LeadCreate(LeadBase):
    pass


class LeadUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    company: str | None = None
    job_title: str | None = None
    source: str | None = None
    status: str | None = None
    notes: str | None = None


class LeadResponse(LeadBase):
    id: int

    model_config = ConfigDict(from_attributes=True)

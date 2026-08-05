from pydantic import BaseModel, ConfigDict, EmailStr


class CustomerBase(BaseModel):
    organization_id: int
    first_name: str
    last_name: str

    email: EmailStr | None = None
    phone: str | None = None
    company: str | None = None
    job_title: str | None = None
    notes: str | None = None


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    company: str | None = None
    job_title: str | None = None
    notes: str | None = None
    is_active: bool | None = None


class CustomerResponse(CustomerBase):
    id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

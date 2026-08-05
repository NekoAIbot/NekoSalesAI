from pydantic import BaseModel, ConfigDict, EmailStr


class ContactBase(BaseModel):
    customer_id: int

    first_name: str
    last_name: str

    email: EmailStr | None = None
    phone: str | None = None

    position: str | None = None
    department: str | None = None

    notes: str | None = None


class ContactCreate(ContactBase):
    pass


class ContactUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    position: str | None = None
    department: str | None = None
    notes: str | None = None
    is_primary: bool | None = None
    is_active: bool |None = None


class ContactResponse(ContactBase):
    id: int
    is_primary: bool
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

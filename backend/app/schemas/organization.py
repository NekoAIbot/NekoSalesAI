from pydantic import BaseModel, ConfigDict, EmailStr


class OrganizationBase(BaseModel):
    name: str
    slug: str
    email: EmailStr | None = None
    phone: str | None = None
    website: str | None = None
    industry: str | None = None
    company_size: str | None = None
    country: str | None = None
    timezone: str = "UTC"
    currency: str = "USD"


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    website: str | None = None
    industry: str | None = None
    company_size: str | None = None
    country: str | None = None
    timezone: str | None = None
    currency: str | None = None
    subscription_plan: str | None = None
    logo: str | None = None
    is_active: bool | None = None


class OrganizationResponse(OrganizationBase):
    id: int
    subscription_plan: str
    logo: str | None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

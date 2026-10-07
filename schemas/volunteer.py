from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from models import VolunteerStatus


class VolunteerCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    phone: str = Field(pattern=r"^0[0-9]{8,9}$")
    district_code: str = Field(pattern=r"^[0-9]{4}$")


class VolunteerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    phone: str
    district_code: str
    status: VolunteerStatus
    approved_at: datetime | None
    created_at: datetime


class VolunteerRegistrationResponse(BaseModel):
    volunteer: VolunteerResponse
    created: bool
    message: str

from uuid import UUID

from pydantic import BaseModel, Field

from services.reports import ReportOutcome

THAILAND_MIN_LATITUDE = 5.5
THAILAND_MAX_LATITUDE = 20.5
THAILAND_MIN_LONGITUDE = 97.3
THAILAND_MAX_LONGITUDE = 105.7


class ReportCreate(BaseModel):
    client_request_id: UUID
    latitude: float = Field(
        ge=THAILAND_MIN_LATITUDE, le=THAILAND_MAX_LATITUDE, allow_inf_nan=False
    )
    longitude: float = Field(
        ge=THAILAND_MIN_LONGITUDE, le=THAILAND_MAX_LONGITUDE, allow_inf_nan=False
    )
    district_code: str = Field(pattern=r"^[0-9]{4}$")
    description: str | None = Field(default=None, max_length=1000)


class ReportResponse(BaseModel):
    report_id: int
    incident_id: int
    outcome: ReportOutcome
    message: str
    emergency_phone: str

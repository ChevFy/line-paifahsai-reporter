from datetime import datetime

from pydantic import BaseModel, ConfigDict

from models import IncidentStatus


class ActiveIncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    latitude: float
    longitude: float
    district_code: str
    status: IncidentStatus
    report_count: int
    created_at: datetime


class ActiveIncidentListResponse(BaseModel):
    generated_at: datetime
    incidents: list[ActiveIncidentResponse]
    truncated: bool
    emergency_phone: str

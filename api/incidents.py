import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Query

from api.reports import EMERGENCY_PHONE
from core.db import SessionLocal
from schemas.incident import ActiveIncidentListResponse, ActiveIncidentResponse
from services.incidents import list_active_incidents

logger = logging.getLogger(__name__)

MAX_ACTIVE_INCIDENTS = 500

router = APIRouter()


@router.get("/incidents/active", response_model=ActiveIncidentListResponse)
async def get_active_incidents(
    district_code: str | None = Query(None, pattern=r"^[0-9]{4}$"),
) -> ActiveIncidentListResponse:
    async with SessionLocal() as session:
        result = await list_active_incidents(
            session, district_code, MAX_ACTIVE_INCIDENTS
        )

    if result.truncated:
        logger.warning(
            "active incidents truncated: limit=%s district_code=%s",
            MAX_ACTIVE_INCIDENTS,
            district_code,
        )

    return ActiveIncidentListResponse(
        generated_at=datetime.now(UTC),
        incidents=[
            ActiveIncidentResponse.model_validate(incident)
            for incident in result.incidents
        ],
        truncated=result.truncated,
        emergency_phone=EMERGENCY_PHONE,
    )

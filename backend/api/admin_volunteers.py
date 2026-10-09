from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from api.admin_auth import CurrentAdmin
from core.db import SessionLocal
from models import VolunteerStatus
from schemas.volunteer import VolunteerPage, VolunteerResponse
from services.volunteers import (
    STATUS_ACTIONS,
    VolunteerNotFoundError,
    count_volunteers,
    list_volunteers,
    set_volunteer_status,
)

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

router = APIRouter(prefix="/admin/volunteers")


@router.get("", response_model=VolunteerPage)
async def get_volunteers(
    admin: CurrentAdmin,
    status: VolunteerStatus | None = None,
    district_code: str | None = Query(None, pattern=r"^[0-9]{4}$"),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
) -> VolunteerPage:
    async with SessionLocal() as session:
        total = await count_volunteers(session, status, district_code)
        volunteers = await list_volunteers(
            session, status, district_code, limit=limit, offset=offset
        )
    return VolunteerPage(
        items=[VolunteerResponse.model_validate(volunteer) for volunteer in volunteers],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/{volunteer_id}/{action}", response_model=VolunteerResponse)
async def change_volunteer_status(
    volunteer_id: int,
    action: Literal["approve", "reject", "suspend"],
    admin: CurrentAdmin,
) -> VolunteerResponse:
    try:
        async with SessionLocal() as session, session.begin():
            volunteer = await set_volunteer_status(
                session,
                volunteer_id,
                STATUS_ACTIONS[action],
                datetime.now(UTC),
                actor=f"admin:{admin.username}",
            )
    except VolunteerNotFoundError:
        raise HTTPException(status_code=404, detail={"message": "ไม่พบจิตอาสา"})
    return VolunteerResponse.model_validate(volunteer)

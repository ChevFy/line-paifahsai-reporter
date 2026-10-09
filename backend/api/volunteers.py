import logging

from fastapi import APIRouter, Header, HTTPException

from api.line_auth import authenticate_liff_user
from core.db import SessionLocal
from models import VolunteerStatus
from schemas.volunteer import (
    VolunteerCreate,
    VolunteerRegistrationResponse,
    VolunteerResponse,
)
from services.volunteers import (
    UnknownDistrictError,
    VolunteerRegistration,
    find_volunteer_by_line_user,
    register_volunteer,
)

logger = logging.getLogger(__name__)

STATUS_MESSAGES = {
    VolunteerStatus.PENDING: "ลงทะเบียนแล้ว รอแอดมินอนุมัติ",
    VolunteerStatus.APPROVED: "คุณเป็นจิตอาสาที่อนุมัติแล้ว จะได้รับแจ้งเหตุในอำเภอของคุณ",
    VolunteerStatus.REJECTED: "การลงทะเบียนไม่ผ่านการอนุมัติ กรุณาติดต่อแอดมิน",
    VolunteerStatus.SUSPENDED: "บัญชีจิตอาสาถูกระงับชั่วคราว กรุณาติดต่อแอดมิน",
}

router = APIRouter()


@router.post("/volunteers", response_model=VolunteerRegistrationResponse)
async def create_volunteer(
    body: VolunteerCreate,
    authorization: str | None = Header(None),
) -> VolunteerRegistrationResponse:
    identity = await authenticate_liff_user(authorization)
    registration = VolunteerRegistration(
        line_user_id=identity.user_id,
        display_name=identity.display_name,
        full_name=body.full_name,
        phone=body.phone,
        district_code=body.district_code,
    )

    try:
        async with SessionLocal() as session, session.begin():
            result = await register_volunteer(session, registration)
    except UnknownDistrictError:
        raise HTTPException(
            status_code=422, detail={"message": "ไม่พบอำเภอที่เลือก กรุณาเลือกใหม่"}
        )

    volunteer = VolunteerResponse.model_validate(result.volunteer)
    return VolunteerRegistrationResponse(
        volunteer=volunteer,
        created=result.created,
        message=STATUS_MESSAGES[volunteer.status],
    )


@router.get("/volunteers/me", response_model=VolunteerRegistrationResponse)
async def get_my_volunteer(
    authorization: str | None = Header(None),
) -> VolunteerRegistrationResponse:
    identity = await authenticate_liff_user(authorization)

    async with SessionLocal() as session:
        found = await find_volunteer_by_line_user(session, identity.user_id)
    if found is None:
        raise HTTPException(
            status_code=404, detail={"message": "ยังไม่ได้ลงทะเบียนเป็นจิตอาสา"}
        )

    volunteer = VolunteerResponse.model_validate(found)
    return VolunteerRegistrationResponse(
        volunteer=volunteer,
        created=False,
        message=STATUS_MESSAGES[volunteer.status],
    )

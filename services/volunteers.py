import logging
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from models import AlertSeverity, District, LineUser, Volunteer, VolunteerStatus
from services.admin_alerts import record_admin_alert

logger = logging.getLogger(__name__)

ALERT_VOLUNTEER_PENDING = "volunteer_pending_approval"


@dataclass(frozen=True)
class VolunteerRegistration:
    line_user_id: str
    display_name: str | None
    full_name: str
    phone: str
    district_code: str


@dataclass(frozen=True)
class RegistrationResult:
    volunteer: Volunteer
    created: bool


class UnknownDistrictError(Exception):
    pass


class VolunteerNotFoundError(Exception):
    pass


class InvalidVolunteerTransitionError(Exception):
    pass


async def register_volunteer(
    session: AsyncSession,
    registration: VolunteerRegistration,
) -> RegistrationResult:
    existing = await find_volunteer_by_line_user(session, registration.line_user_id)
    if existing is not None:
        logger.info(
            "volunteer already registered: id=%s status=%s",
            existing.id,
            existing.status,
        )
        return RegistrationResult(volunteer=existing, created=False)

    if await session.get(District, registration.district_code) is None:
        raise UnknownDistrictError(registration.district_code)

    line_user = insert(LineUser).values(
        user_id=registration.line_user_id,
        display_name=registration.display_name,
    )
    await session.execute(
        line_user.on_conflict_do_update(
            index_elements=[LineUser.user_id],
            set_={
                "display_name": sa.func.coalesce(
                    line_user.excluded.display_name, LineUser.display_name
                )
            },
        )
    )

    volunteer = Volunteer(
        line_user_id=registration.line_user_id,
        full_name=registration.full_name,
        phone=registration.phone,
        district_code=registration.district_code,
    )
    session.add(volunteer)
    await session.flush()
    await session.refresh(volunteer)

    await record_admin_alert(
        session,
        alert_type=ALERT_VOLUNTEER_PENDING,
        severity=AlertSeverity.WARNING,
        message=(
            f"จิตอาสาสมัครใหม่ {registration.full_name} อำเภอ {registration.district_code} "
            "รออนุมัติ"
        ),
        payload={"volunteer_id": volunteer.id, "district_code": volunteer.district_code},
        dedup_key=f"{ALERT_VOLUNTEER_PENDING}:{volunteer.id}",
    )
    logger.info(
        "volunteer registered: id=%s district=%s",
        volunteer.id,
        volunteer.district_code,
    )
    return RegistrationResult(volunteer=volunteer, created=True)


async def find_volunteer_by_line_user(
    session: AsyncSession,
    line_user_id: str,
) -> Volunteer | None:
    statement = sa.select(Volunteer).where(Volunteer.line_user_id == line_user_id)
    return (await session.execute(statement)).scalar_one_or_none()


async def list_volunteers(
    session: AsyncSession,
    status: VolunteerStatus | None = None,
) -> list[Volunteer]:
    statement = sa.select(Volunteer).order_by(Volunteer.created_at, Volunteer.id)
    if status is not None:
        statement = statement.where(Volunteer.status == status)
    return list((await session.execute(statement)).scalars().all())


async def set_volunteer_status(
    session: AsyncSession,
    volunteer_id: int,
    status: VolunteerStatus,
    now: datetime,
) -> Volunteer:
    volunteer = await session.get(Volunteer, volunteer_id, with_for_update=True)
    if volunteer is None:
        raise VolunteerNotFoundError(volunteer_id)
    if status == VolunteerStatus.PENDING:
        raise InvalidVolunteerTransitionError("cannot move volunteer back to pending")

    previous = volunteer.status
    volunteer.status = status
    if status == VolunteerStatus.APPROVED and volunteer.approved_at is None:
        volunteer.approved_at = now
    await session.flush()

    logger.info(
        "volunteer status changed: id=%s %s -> %s",
        volunteer.id,
        previous,
        status,
    )
    return volunteer


async def approved_line_user_ids_in_district(
    session: AsyncSession,
    district_code: str,
) -> list[str]:
    statement = (
        sa.select(Volunteer.line_user_id)
        .join(LineUser, LineUser.user_id == Volunteer.line_user_id)
        .where(
            Volunteer.district_code == district_code,
            Volunteer.status == VolunteerStatus.APPROVED,
            LineUser.is_blocked.is_(False),
        )
        .order_by(Volunteer.id)
    )
    return list((await session.execute(statement)).scalars().all())

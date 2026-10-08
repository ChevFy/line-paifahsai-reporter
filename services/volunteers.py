import logging
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from models import AlertSeverity, District, LineUser, Volunteer, VolunteerStatus
from services.admin_alerts import acknowledge_admin_alert, record_admin_alert
from services.jobs import enqueue_job

logger = logging.getLogger(__name__)

ALERT_VOLUNTEER_PENDING = "volunteer_pending_approval"
JOB_VOLUNTEER_STATUS_NOTICE = "volunteer_status_notice"

STATUS_ACTIONS = {
    "approve": VolunteerStatus.APPROVED,
    "reject": VolunteerStatus.REJECTED,
    "suspend": VolunteerStatus.SUSPENDED,
}


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


@dataclass(frozen=True)
class VolunteerNotice:
    line_user_id: str
    status: VolunteerStatus
    district_name: str


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


def volunteer_filters(
    status: VolunteerStatus | None,
    district_code: str | None,
) -> list[sa.ColumnElement[bool]]:
    conditions = []
    if status is not None:
        conditions.append(Volunteer.status == status)
    if district_code is not None:
        conditions.append(Volunteer.district_code == district_code)
    return conditions


async def list_volunteers(
    session: AsyncSession,
    status: VolunteerStatus | None = None,
    district_code: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[Volunteer]:
    statement = (
        sa.select(Volunteer)
        .where(*volunteer_filters(status, district_code))
        .order_by(Volunteer.created_at, Volunteer.id)
        .limit(limit)
        .offset(offset)
    )
    return list((await session.execute(statement)).scalars().all())


async def count_volunteers(
    session: AsyncSession,
    status: VolunteerStatus | None = None,
    district_code: str | None = None,
) -> int:
    statement = (
        sa.select(sa.func.count())
        .select_from(Volunteer)
        .where(*volunteer_filters(status, district_code))
    )
    return (await session.execute(statement)).scalar_one()


async def set_volunteer_status(
    session: AsyncSession,
    volunteer_id: int,
    status: VolunteerStatus,
    now: datetime,
    actor: str = "unknown",
) -> Volunteer:
    volunteer = await session.get(Volunteer, volunteer_id, with_for_update=True)
    if volunteer is None:
        raise VolunteerNotFoundError(volunteer_id)
    if status == VolunteerStatus.PENDING:
        raise InvalidVolunteerTransitionError("cannot move volunteer back to pending")

    previous = volunteer.status
    if previous == status:
        logger.info(
            "volunteer status unchanged: id=%s status=%s actor=%s",
            volunteer.id,
            status,
            actor,
        )
        return volunteer

    volunteer.status = status
    if status == VolunteerStatus.APPROVED and volunteer.approved_at is None:
        volunteer.approved_at = now
    await session.flush()

    if previous == VolunteerStatus.PENDING:
        await acknowledge_admin_alert(
            session, f"{ALERT_VOLUNTEER_PENDING}:{volunteer.id}", actor, now
        )
    await enqueue_job(
        session,
        JOB_VOLUNTEER_STATUS_NOTICE,
        {
            "volunteer_id": volunteer.id,
            "status": status.value,
            "changed_at": now.isoformat(),
        },
        idempotency_key=(
            f"{JOB_VOLUNTEER_STATUS_NOTICE}:{volunteer.id}:{status.value}:{now.isoformat()}"
        ),
    )

    logger.info(
        "volunteer status changed: id=%s %s -> %s actor=%s",
        volunteer.id,
        previous,
        status,
        actor,
    )
    return volunteer


async def load_volunteer_notice(
    session: AsyncSession,
    volunteer_id: int,
) -> VolunteerNotice | None:
    statement = (
        sa.select(Volunteer.line_user_id, Volunteer.status, District.name_th)
        .join(District, District.code == Volunteer.district_code)
        .where(Volunteer.id == volunteer_id)
    )
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        return None
    return VolunteerNotice(
        line_user_id=row.line_user_id,
        status=row.status,
        district_name=row.name_th,
    )


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

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

BANGKOK = ZoneInfo("Asia/Bangkok")
OPS_DAY_START_OFFSET = timedelta(hours=6)


def ops_date_for(moment: datetime) -> date:
    if moment.tzinfo is None:
        raise ValueError("moment must be timezone-aware")
    return (moment.astimezone(BANGKOK) - OPS_DAY_START_OFFSET).date()

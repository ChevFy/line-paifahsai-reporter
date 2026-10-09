from datetime import UTC, date, datetime

import pytest

from services.ops_date import BANGKOK, ops_date_for


def test_before_six_am_belongs_to_previous_ops_day():
    moment = datetime(2026, 3, 2, 5, 59, tzinfo=BANGKOK)
    assert ops_date_for(moment) == date(2026, 3, 1)


def test_six_am_starts_new_ops_day():
    moment = datetime(2026, 3, 2, 6, 0, tzinfo=BANGKOK)
    assert ops_date_for(moment) == date(2026, 3, 2)


def test_utc_input_is_converted_to_bangkok():
    moment = datetime(2026, 3, 1, 23, 30, tzinfo=UTC)
    assert ops_date_for(moment) == date(2026, 3, 2)


def test_naive_datetime_is_rejected():
    with pytest.raises(ValueError):
        ops_date_for(datetime(2026, 3, 2, 7, 0))

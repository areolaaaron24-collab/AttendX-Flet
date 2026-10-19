from datetime import date, datetime, time, timedelta

from attendx.core.attendance_rules import MANILA, calculate_attendance_status, is_session_ended


def dt_at(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 10, 16, hour, minute, second, tzinfo=MANILA)


def test_exact_start_is_present_and_pre_start_scan_is_rejected():
    import pytest
    with pytest.raises(ValueError, match="before the scheduled start time"):
        calculate_attendance_status(time(8, 0), dt_at(7, 59, 59))
    assert calculate_attendance_status("08:00:00", dt_at(8, 0, 0)) == "PRESENT"


def test_late_boundaries_are_second_accurate():
    assert calculate_attendance_status("08:00", dt_at(8, 0, 1)) == "LATE"
    assert calculate_attendance_status("08:00", dt_at(8, 14, 59)) == "LATE"
    assert calculate_attendance_status("08:00", dt_at(8, 15, 0)) == "LATE_ABSENT"
    assert calculate_attendance_status("08:00", dt_at(8, 15, 1)) == "LATE_ABSENT"


def test_status_uses_manila_date_after_timezone_conversion():
    utc_value = datetime(2026, 10, 16, 0, 0, 0, tzinfo=__import__("datetime").timezone.utc)
    assert utc_value.astimezone(MANILA).date() == date(2026, 10, 16)
    assert calculate_attendance_status(time(8, 0), utc_value) == "PRESENT"


def test_session_end_boundary_is_inclusive():
    session_date = date(2026, 10, 16)
    assert not is_session_ended(session_date, "09:00", dt_at(8, 59, 59))
    assert is_session_ended(session_date, "09:00", dt_at(9, 0, 0))
    assert is_session_ended(session_date, time(9, 0), dt_at(9, 0, 1))

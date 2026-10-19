from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

MANILA = ZoneInfo("Asia/Manila")
GRACE_SECONDS = 15 * 60


def calculate_attendance_status(
    scheduled_start: time | str,
    observed_at: datetime,
    timezone: ZoneInfo = MANILA,
) -> str:
    """Return the approved status using second-accurate 15-minute boundaries.

    A scan before the scheduled start is rejected with ValueError. The exact scheduled
    start is PRESENT; start+1 second through start+14:59 is LATE; start+15:00 onward
    is LATE_ABSENT. ABSENT is inserted only by session finalization when no valid
    attendance record exists.
    """
    if isinstance(scheduled_start, str):
        parts = [int(part) for part in scheduled_start.split(":")]
        start = time(parts[0], parts[1], parts[2] if len(parts) > 2 else 0)
    else:
        start = scheduled_start
    local = observed_at.astimezone(timezone) if observed_at.tzinfo else observed_at.replace(tzinfo=timezone)
    start_dt = datetime.combine(local.date(), start, tzinfo=timezone)
    elapsed = (local - start_dt).total_seconds()
    if elapsed < 0:
        raise ValueError("Attendance cannot be recorded before the scheduled start time.")
    if elapsed == 0:
        return "PRESENT"
    if elapsed < GRACE_SECONDS:
        return "LATE"
    return "LATE_ABSENT"


def is_session_ended(session_date: date, end_time: time | str, now: datetime) -> bool:
    if isinstance(end_time, str):
        parts = [int(part) for part in end_time.split(":")]
        end = time(parts[0], parts[1], parts[2] if len(parts) > 2 else 0)
    else:
        end = end_time
    local = now.astimezone(MANILA) if now.tzinfo else now.replace(tzinfo=MANILA)
    return local >= datetime.combine(session_date, end, tzinfo=MANILA)


def local_now() -> datetime:
    return datetime.now(MANILA)

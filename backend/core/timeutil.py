"""Time and timezone utilities for VyapaarAI.
Rule 2: Time is stored as UTC. Display in IST (Asia/Kolkata).
Naive input timestamps from merchants/data are assumed IST.
A "day" means an IST day: convert day boundaries to UTC before querying.
"""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc


def to_utc(dt: datetime) -> datetime:
    """Convert datetime to UTC. Naive datetime is assumed to be in IST (input data)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(UTC)


def to_ist(dt: datetime) -> datetime:
    """Convert datetime to IST. Naive datetime is assumed to be in IST."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(IST)


def utc_to_ist(dt: datetime) -> datetime:
    """Convert a database UTC datetime (which may be naive in SQLite) to IST."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(IST)


def ist_day_bounds_utc(d: date) -> tuple[datetime, datetime]:
    """Given an IST calendar date, returns (start_utc, end_utc)
    where start_utc is inclusive (00:00:00 IST in UTC)
    and end_utc is exclusive (00:00:00 IST of next day in UTC).
    """
    start_ist = datetime.combine(d, time.min, tzinfo=IST)
    end_ist = datetime.combine(d + timedelta(days=1), time.min, tzinfo=IST)
    return start_ist.astimezone(UTC), end_ist.astimezone(UTC)

"""
Centralized Timezone Management: India Standard Time (Asia/Kolkata, UTC+05:30)

Guarantees:
- Timestamps stored consistently in UTC.
- Conversions to and from Asia/Kolkata (IST).
- Correct IST calendar date boundary mapping to UTC for database queries.
- Consistent IST string formatting: e.g. "17 Nov 2026, 06:45 PM IST".
"""

from zoneinfo import ZoneInfo
from datetime import datetime, date, time, timezone, timedelta
from typing import Union, Tuple, Optional

# Standard IANA Timezone for India
IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc


def utc_now() -> datetime:
    """Return current naive UTC datetime for database storage."""
    return datetime.utcnow()


def ist_now() -> datetime:
    """Return current timezone-aware datetime in Asia/Kolkata."""
    return datetime.now(IST)


def to_ist(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Convert a datetime (naive UTC or aware) to an Asia/Kolkata timezone-aware datetime.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        # Naive datetime from SQLite is assumed UTC
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(IST)


def to_ist_str(dt: Optional[datetime], fmt: str = "%d %b %Y, %I:%M %p IST") -> str:
    """
    Format a datetime as an IST string. Returns empty string if dt is None.
    Example: '17 Nov 2026, 06:45 PM IST'
    """
    if dt is None:
        return ""
    ist_dt = to_ist(dt)
    return ist_dt.strftime(fmt)


def to_ist_date_str(dt: Optional[datetime], fmt: str = "%Y-%m-%d") -> str:
    """Format a datetime as an IST date string (YYYY-MM-DD)."""
    if dt is None:
        return ""
    ist_dt = to_ist(dt)
    return ist_dt.strftime(fmt)


def get_ist_day_bounds_in_utc(target_date: Union[str, date, datetime]) -> Tuple[datetime, datetime]:
    """
    Given a calendar date in Asia/Kolkata, calculate the exact UTC interval [start_utc, end_utc]
    for querying UTC-stored records.
    
    Example:
    2026-11-17 in IST:
      Start: 2026-11-17 00:00:00 IST -> 2026-11-16 18:30:00 UTC
      End:   2026-11-17 23:59:59.999999 IST -> 2026-11-17 18:29:59.999999 UTC
    """
    if isinstance(target_date, str):
        target_date = datetime.strptime(target_date.strip()[:10], "%Y-%m-%d").date()
    elif isinstance(target_date, datetime):
        target_date = to_ist(target_date).date()
    
    start_ist = datetime.combine(target_date, time.min, tzinfo=IST)
    end_ist = datetime.combine(target_date, time.max, tzinfo=IST)
    
    start_utc = start_ist.astimezone(UTC).replace(tzinfo=None)
    end_utc = end_ist.astimezone(UTC).replace(tzinfo=None)
    
    return start_utc, end_utc


def get_ist_today_bounds_in_utc() -> Tuple[datetime, datetime]:
    """Return UTC start and end bounds for today in Asia/Kolkata."""
    return get_ist_day_bounds_in_utc(ist_now().date())


def get_ist_yesterday_bounds_in_utc() -> Tuple[datetime, datetime]:
    """Return UTC start and end bounds for yesterday in Asia/Kolkata."""
    yesterday = ist_now().date() - timedelta(days=1)
    return get_ist_day_bounds_in_utc(yesterday)


def get_ist_week_bounds_in_utc() -> Tuple[datetime, datetime]:
    """
    Return UTC start and end bounds for current week (Monday to Sunday) in Asia/Kolkata.
    """
    today = ist_now().date()
    monday = today - timedelta(days=today.weekday())
    start_ist = datetime.combine(monday, time.min, tzinfo=IST)
    
    now_ist = ist_now()
    end_ist = datetime.combine(today, time.max, tzinfo=IST)
    
    return start_ist.astimezone(UTC).replace(tzinfo=None), end_ist.astimezone(UTC).replace(tzinfo=None)


def get_ist_month_bounds_in_utc() -> Tuple[datetime, datetime]:
    """
    Return UTC start and end bounds for the 1st of current month up to end of today in Asia/Kolkata.
    """
    today = ist_now().date()
    first_of_month = today.replace(day=1)
    start_ist = datetime.combine(first_of_month, time.min, tzinfo=IST)
    end_ist = datetime.combine(today, time.max, tzinfo=IST)
    
    return start_ist.astimezone(UTC).replace(tzinfo=None), end_ist.astimezone(UTC).replace(tzinfo=None)

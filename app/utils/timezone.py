import datetime
from datetime import timezone, timedelta

# Indian Standard Time (IST) is UTC+05:30
try:
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")
except Exception:
    IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime.datetime:
    """Returns current datetime in Indian Standard Time (IST)."""
    return datetime.datetime.now(timezone.utc).astimezone(IST)


def to_ist(dt, fmt=None):
    """
    Converts a datetime, date, or ISO timestamp string to Indian Standard Time (IST).
    If fmt is specified, returns formatted string (e.g. '%d %b %Y, %I:%M %p').
    If fmt is None, returns the timezone-aware datetime in IST.
    If dt is empty/None, returns empty string if fmt is specified, else None.
    """
    if not dt:
        return "" if fmt else None

    if isinstance(dt, str):
        try:
            dt = datetime.datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return dt

    if isinstance(dt, datetime.date) and not isinstance(dt, datetime.datetime):
        if fmt:
            return dt.strftime(fmt)
        return dt

    if isinstance(dt, datetime.datetime):
        if dt.tzinfo is None:
            # Stored as naive UTC in database
            dt = dt.replace(tzinfo=timezone.utc)
        dt_ist = dt.astimezone(IST)
        if fmt:
            return dt_ist.strftime(fmt)
        return dt_ist

    return dt


def format_ist(dt, fmt="%d %b %Y, %I:%M %p"):
    """Formats a datetime in Indian Standard Time."""
    return to_ist(dt, fmt=fmt)


def to_ist_iso(dt):
    """Returns an ISO 8601 string representation with IST offset (+05:30)."""
    if not dt:
        return None
    ist_dt = to_ist(dt, fmt=None)
    if isinstance(ist_dt, datetime.datetime):
        return ist_dt.isoformat()
    return str(dt)

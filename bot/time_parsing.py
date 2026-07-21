import re
from datetime import datetime
from zoneinfo import available_timezones

# Building this lookup once at import time is much faster than scanning
# available_timezones() (thousands of names) on every message.
_KNOWN_TIMEZONES = {name.lower(): name for name in available_timezones()}

_UTC_OFFSET_RE = re.compile(r"^utc\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?$", re.IGNORECASE)

_TIME_FORMATS = ["%I:%M %p", "%I %p", "%H:%M", "%H"]


def parse_timezone(text: str) -> str | None:
    """Accepts an IANA name ("America/New_York") or a UTC offset ("UTC+8", "UTC-5:30")."""
    cleaned = text.strip()

    known = _KNOWN_TIMEZONES.get(cleaned.lower())
    if known:
        return known

    match = _UTC_OFFSET_RE.match(cleaned)
    if match:
        sign, hours, minutes = match.groups()
        return f"UTC{sign}{int(hours):02d}:{int(minutes or 0):02d}"

    return None


def parse_time_of_day(text: str) -> str | None:
    """Accepts things like "8:00 AM", "8am", "20:00" and returns 24-hour "HH:MM"."""
    cleaned = text.strip().upper().replace(".", "")
    cleaned = re.sub(r"(\d)(AM|PM)", r"\1 \2", cleaned)

    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).strftime("%H:%M")
        except ValueError:
            continue
    return None

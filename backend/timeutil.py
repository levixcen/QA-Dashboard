from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional, Union
from zoneinfo import ZoneInfo

JAKARTA = ZoneInfo("Asia/Jakarta")
UTC = timezone.utc

DateLike = Union[str, datetime, date, int, float, None]


def now_utc() -> datetime:
    return datetime.now(UTC)


def now_jakarta() -> datetime:
    return datetime.now(JAKARTA)


def now_iso() -> str:
    """UTC ISO timestamp with second precision (for created_at / updated_at)."""
    return now_utc().replace(microsecond=0).isoformat()


def today_jakarta() -> str:
    """Jakarta calendar date as YYYY-MM-DD."""
    return now_jakarta().date().isoformat()


def period_jakarta() -> str:
    """Current Jakarta year-month as YYYY-MM."""
    d = now_jakarta().date()
    return f"{d.year:04d}-{d.month:02d}"


def run_date_from_start_ts(start_ts_ms: Optional[Union[int, float]]) -> str:
    """Jakarta calendar day for an Allure start timestamp (milliseconds)."""
    if not start_ts_ms:
        return today_jakarta()
    try:
        ts = float(start_ts_ms) / 1000.0
    except (TypeError, ValueError):
        return today_jakarta()
    return datetime.fromtimestamp(ts, tz=UTC).astimezone(JAKARTA).date().isoformat()


def period_from_date(date_str: Optional[str]) -> Optional[str]:
    """YYYY-MM from a YYYY-MM-DD (or already YYYY-MM) string."""
    if not date_str:
        return None
    s = str(date_str).strip()
    if len(s) >= 7 and s[4] == "-":
        return s[:7]
    return None


def parse_to_utc(value: DateLike) -> Optional[datetime]:
    """Best-effort parse of stored values into an aware UTC datetime."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime(value.year, value.month, value.day, tzinfo=JAKARTA).astimezone(UTC)
    if isinstance(value, (int, float)):
        # Treat large numbers as ms (Allure), small as seconds.
        ts = float(value)
        if ts > 1e12:
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=UTC)
    s = str(value).strip()
    if not s:
        return None
    # Bare date → interpret as Jakarta midnight.
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        try:
            y, m, d = int(s[0:4]), int(s[5:7]), int(s[8:10])
            return datetime(y, m, d, tzinfo=JAKARTA).astimezone(UTC)
        except ValueError:
            return None
    # ISO-ish
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            # Legacy naive timestamps: treat as UTC (previous app behaviour).
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except ValueError:
        return None


def to_jakarta(value: DateLike) -> Optional[datetime]:
    dt = parse_to_utc(value)
    return dt.astimezone(JAKARTA) if dt else None


def format_display_date(value: DateLike, *, with_time: bool = False) -> str:
    """Human-readable Jakarta date for UI (e.g. 'Oct 5' or 'Oct 5, 14:30')."""
    dt = to_jakarta(value)
    if not dt:
        return "—"
    if with_time:
        return dt.strftime("%b %-d, %H:%M") if hasattr(dt, "strftime") else dt.strftime("%b %d, %H:%M")
    # Cross-platform: avoid %-d on Windows; strip leading zero manually.
    return f"{dt.strftime('%b')} {dt.day}"


def format_iso_date(value: DateLike) -> Optional[str]:
    """YYYY-MM-DD in Jakarta, or None."""
    dt = to_jakarta(value)
    return dt.date().isoformat() if dt else None
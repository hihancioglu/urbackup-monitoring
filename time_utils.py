import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _resolve_timezone() -> timezone | ZoneInfo:
    tz_name = (os.getenv("URB_TIMEZONE") or "Europe/Istanbul").strip()
    if tz_name.upper() in {"UTC+3", "UTC+03", "UTC+03:00", "GMT+3", "GMT+03:00"}:
        return timezone(timedelta(hours=3))

    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=3))


APP_TIMEZONE = _resolve_timezone()


def now_local() -> datetime:
    return datetime.now(APP_TIMEZONE)


def from_unix(timestamp: int | float | str | None) -> datetime | None:
    if timestamp in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(timestamp), APP_TIMEZONE)
    except (TypeError, ValueError, OSError):
        return None


def iso_now_local() -> str:
    return now_local().isoformat(timespec="seconds")

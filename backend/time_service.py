from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .models import Profile


def utc_now() -> datetime:
    return datetime.now(UTC)


def active_timezone(profile: Profile, now_utc: datetime | None = None) -> str:
    now_utc = now_utc or utc_now()
    expires = profile.temporary_timezone_expires_at
    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if profile.temporary_timezone and expires and expires > now_utc:
        return profile.temporary_timezone
    return profile.timezone


def resolve_local_datetime(local_value: datetime, timezone_name: str) -> datetime:
    """Resolve wall time using first occurrence; skipped times move to next valid minute."""
    if local_value.tzinfo is not None:
        raise ValueError("Expected a naive local datetime")
    zone = ZoneInfo(timezone_name)
    candidate = local_value
    for _ in range(181):
        aware = candidate.replace(tzinfo=zone, fold=0)
        roundtrip = aware.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
        if roundtrip == candidate:
            return aware
        candidate += timedelta(minutes=1)
    raise ValueError("Could not resolve local time")


class UserClock:
    def __init__(
        self,
        profile: Profile,
        now_provider: Callable[[], datetime] = utc_now,
    ):
        self.profile = profile
        self.now_provider = now_provider

    @property
    def timezone_name(self) -> str:
        return active_timezone(self.profile, self.now_provider())

    def now_utc(self) -> datetime:
        value = self.now_provider()
        return value if value.tzinfo else value.replace(tzinfo=UTC)

    def now(self) -> datetime:
        return self.now_utc().astimezone(ZoneInfo(self.timezone_name))

    def local_date(self) -> date:
        return self.now().date()

    def local_to_utc(self, value: datetime) -> datetime:
        return resolve_local_datetime(value, self.timezone_name).astimezone(UTC)

    def utc_to_local(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(ZoneInfo(self.timezone_name))

    def start_of_day_utc(self, day: date) -> datetime:
        return self.local_to_utc(datetime.combine(day, time.min))

    def end_of_day_utc(self, day: date) -> datetime:
        return self.start_of_day_utc(day + timedelta(days=1))


def next_scheduled_occurrence(
    *,
    after_utc: datetime,
    local_time: time,
    days_of_week: set[int],
    timezone_name: str,
) -> datetime:
    if after_utc.tzinfo is None:
        after_utc = after_utc.replace(tzinfo=UTC)
    local_after = after_utc.astimezone(ZoneInfo(timezone_name))
    for offset in range(8):
        day = local_after.date() + timedelta(days=offset)
        if day.weekday() not in days_of_week:
            continue
        candidate = resolve_local_datetime(datetime.combine(day, local_time), timezone_name)
        candidate_utc = candidate.astimezone(UTC)
        if candidate_utc > after_utc:
            return candidate_utc
    raise ValueError("Schedule has no enabled weekday")


def is_quiet_time(value: time, start: time | None, end: time | None) -> bool:
    if start is None or end is None or start == end:
        return False
    if start < end:
        return start <= value < end
    return value >= start or value < end


def quiet_period_end_utc(
    value_utc: datetime,
    timezone_name: str,
    start: time,
    end: time,
) -> datetime:
    """Return the UTC end of the quiet period containing value_utc."""
    if value_utc.tzinfo is None:
        value_utc = value_utc.replace(tzinfo=UTC)
    local = value_utc.astimezone(ZoneInfo(timezone_name))
    if not is_quiet_time(local.time(), start, end):
        return value_utc
    end_day = local.date()
    if start > end and local.time() >= start:
        end_day += timedelta(days=1)
    return resolve_local_datetime(
        datetime.combine(end_day, end), timezone_name
    ).astimezone(UTC)

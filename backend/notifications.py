from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import get_config
from .models import NotificationDelivery, Profile, ReminderRule, UserSetting
from .time_service import (
    active_timezone,
    is_quiet_time,
    next_scheduled_occurrence,
    quiet_period_end_utc,
    utc_now,
)


class NotificationSender(Protocol):
    def send(self, target: str, title: str, message: str) -> tuple[bool, str | None]: ...


class HomeAssistantNotificationSender:
    def send(self, target: str, title: str, message: str) -> tuple[bool, str | None]:
        cfg = get_config()
        if not cfg.supervisor_token:
            return False, "Home Assistant delivery is unavailable"
        service = target.removeprefix("notify.")
        try:
            response = httpx.post(
                f"{cfg.supervisor_api_url.rstrip('/')}/api/services/notify/{service}",
                headers={"Authorization": f"Bearer {cfg.supervisor_token}"},
                json={"title": title, "message": message},
                timeout=8,
            )
            if response.is_success:
                return True, None
            return False, f"Home Assistant returned HTTP {response.status_code}"
        except Exception as exc:
            return False, str(exc)


def rule_timezone(rule: ReminderRule, profile: Profile, at_utc: datetime) -> str:
    if rule.timezone_behavior == "fixed_timezone" and rule.fixed_timezone:
        return rule.fixed_timezone
    return active_timezone(profile, at_utc)


def calculate_next_run(rule: ReminderRule, profile: Profile, after_utc: datetime) -> datetime | None:
    if not rule.enabled or not rule.local_time:
        return None
    days = {int(value) for value in rule.days_of_week.split(",") if value.strip()}
    timezone_name = rule_timezone(rule, profile, after_utc)
    result = next_scheduled_occurrence(
        after_utc=after_utc,
        local_time=rule.local_time,
        days_of_week=days,
        timezone_name=timezone_name,
    )
    expires = profile.temporary_timezone_expires_at
    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if timezone_name != profile.timezone and expires and result >= expires:
        return next_scheduled_occurrence(
            after_utc=after_utc,
            local_time=rule.local_time,
            days_of_week=days,
            timezone_name=profile.timezone,
        )
    return result


def recalculate_user_reminders(db: Session, profile: Profile, now: datetime | None = None) -> None:
    now = now or utc_now()
    for rule in db.scalars(
        select(ReminderRule).where(ReminderRule.profile_id == profile.id)
    ):
        rule.next_run_at_utc = calculate_next_run(rule, profile, now)
        rule.updated_at = now


def _user_settings(db: Session, profile_id: int) -> dict[str, str]:
    return {
        item.key: item.value
        for item in db.scalars(
            select(UserSetting).where(UserSetting.profile_id == profile_id)
        )
    }


def _setting_time(value: str | None) -> time | None:
    if not value:
        return None
    try:
        return time.fromisoformat(value)
    except ValueError:
        return None


def _setting_bool(value: str | None) -> bool:
    return (value or "").lower() == "true"


def process_due_reminders(
    db: Session,
    sender: NotificationSender,
    now: datetime | None = None,
) -> int:
    now = now or utc_now()
    due = list(
        db.scalars(
            select(ReminderRule)
            .where(
                ReminderRule.enabled,
                ReminderRule.next_run_at_utc.is_not(None),
                ReminderRule.next_run_at_utc <= now,
            )
            .order_by(ReminderRule.next_run_at_utc)
        )
    )
    processed = 0
    for rule in due:
        profile = db.get(Profile, rule.profile_id)
        scheduled = rule.next_run_at_utc
        if not profile or not scheduled:
            continue
        if scheduled.tzinfo is None:
            scheduled = scheduled.replace(tzinfo=UTC)
        settings = _user_settings(db, profile.id)
        if _setting_bool(settings.get("reminders_paused")):
            rule.next_run_at_utc = None
            rule.updated_at = now
            db.commit()
            continue
        snoozed_until = rule.snoozed_until
        if snoozed_until and snoozed_until.tzinfo is None:
            snoozed_until = snoozed_until.replace(tzinfo=UTC)
        if snoozed_until and snoozed_until > now:
            rule.next_run_at_utc = snoozed_until
            rule.updated_at = now
            db.commit()
            continue
        timezone_name = rule_timezone(rule, profile, scheduled)
        local_scheduled = scheduled.astimezone(ZoneInfo(timezone_name))
        weekend_behavior = (
            settings.get("friday_reminders", "gentle")
            if local_scheduled.weekday() == 4
            else settings.get("saturday_reminders", "gentle")
            if local_scheduled.weekday() == 5
            else "normal"
        )
        if weekend_behavior == "paused":
            rule.next_run_at_utc = calculate_next_run(
                rule, profile, max(now, scheduled) + timedelta(seconds=1)
            )
            rule.updated_at = now
            db.commit()
            continue
        quiet_start = rule.quiet_start or _setting_time(settings.get("quiet_hours_start"))
        quiet_end = rule.quiet_end or _setting_time(settings.get("quiet_hours_end"))
        bypass_quiet = rule.urgent_bypasses_quiet_hours and _setting_bool(
            settings.get("urgent_bypasses_quiet_hours")
        )
        local_now = now.astimezone(ZoneInfo(timezone_name))
        if (
            quiet_start
            and quiet_end
            and not bypass_quiet
            and is_quiet_time(local_now.time(), quiet_start, quiet_end)
        ):
            rule.next_run_at_utc = quiet_period_end_utc(
                now, timezone_name, quiet_start, quiet_end
            )
            rule.updated_at = now
            db.commit()
            continue
        delivery = NotificationDelivery(
            rule_id=rule.id,
            profile_id=profile.id,
            scheduled_for_utc=scheduled,
            attempted_at_utc=now,
        )
        db.add(delivery)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            continue
        target_setting = db.get(UserSetting, (profile.id, "notification_target"))
        target = target_setting.value.strip() if target_setting else ""
        if not target:
            delivery.status = "unavailable"
            delivery.error = "No notification target is configured"
        else:
            title = (
                "A gentle Health OS reminder"
                if weekend_behavior == "gentle"
                else "Health OS reminder"
            )
            success, error = sender.send(target, title, rule.key)
            delivery.status = "sent" if success else "unavailable"
            delivery.error = error
            if success:
                rule.last_sent_at_utc = now
        rule.next_run_at_utc = calculate_next_run(
            rule, profile, max(now, scheduled) + timedelta(seconds=1)
        )
        rule.updated_at = now
        db.commit()
        processed += 1
    return processed

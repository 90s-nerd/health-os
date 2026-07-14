from datetime import UTC, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend import models
from backend.database import engine
from backend.notifications import process_due_reminders, recalculate_user_reminders
from backend.services import ensure_tasks, seed_profile
from backend.time_service import (
    UserClock,
    active_timezone,
    is_quiet_time,
    next_scheduled_occurrence,
    quiet_period_end_utc,
    resolve_local_datetime,
)


def profile(timezone_name: str) -> models.Profile:
    return models.Profile(
        display_name="Time test",
        timezone=timezone_name,
        timezone_source="user_selected",
        onboarding_completed=True,
    )


def test_same_utc_instant_maps_to_each_users_local_time_and_date():
    instant = datetime(2026, 7, 14, 5, 30, tzinfo=UTC)
    chicago = UserClock(profile("America/Chicago"), lambda: instant)
    denver = UserClock(profile("America/Denver"), lambda: instant)
    assert chicago.now().strftime("%H:%M") == "00:30"
    assert denver.now().strftime("%H:%M") == "23:30"
    assert chicago.local_date().isoformat() == "2026-07-14"
    assert denver.local_date().isoformat() == "2026-07-13"


def test_local_weekday_rules_follow_each_users_timezone():
    instant = datetime(2026, 7, 18, 5, 30, tzinfo=UTC)
    chicago = UserClock(profile("America/Chicago"), lambda: instant)
    phoenix = UserClock(profile("America/Phoenix"), lambda: instant)
    assert chicago.local_date().weekday() == 5
    assert phoenix.local_date().weekday() == 4
    sunday_instant = datetime(2026, 7, 19, 6, 30, tzinfo=UTC)
    assert UserClock(profile("America/Chicago"), lambda: sunday_instant).local_date().weekday() == 6
    assert UserClock(profile("America/Los_Angeles"), lambda: sunday_instant).local_date().weekday() == 5


def test_travel_timezone_expires_back_to_home_timezone():
    user = profile("America/Chicago")
    user.temporary_timezone = "America/Denver"
    user.temporary_timezone_expires_at = datetime(2026, 7, 20, tzinfo=UTC)
    assert active_timezone(user, datetime(2026, 7, 19, tzinfo=UTC)) == "America/Denver"
    assert active_timezone(user, datetime(2026, 7, 21, tzinfo=UTC)) == "America/Chicago"


def test_dst_spring_forward_moves_to_next_valid_time_once():
    resolved = resolve_local_datetime(
        datetime(2026, 3, 8, 2, 30), "America/Chicago"
    )
    assert resolved.strftime("%H:%M") == "03:00"
    occurrence = next_scheduled_occurrence(
        after_utc=datetime(2026, 3, 8, 6, 0, tzinfo=UTC),
        local_time=time(2, 30),
        days_of_week={6},
        timezone_name="America/Chicago",
    )
    assert occurrence == datetime(2026, 3, 8, 8, 0, tzinfo=UTC)


def test_dst_fall_back_uses_first_occurrence_only():
    occurrence = next_scheduled_occurrence(
        after_utc=datetime(2026, 11, 1, 5, 0, tzinfo=UTC),
        local_time=time(1, 30),
        days_of_week={6},
        timezone_name="America/Chicago",
    )
    assert occurrence == datetime(2026, 11, 1, 6, 30, tzinfo=UTC)


def test_quiet_hours_cross_midnight():
    assert is_quiet_time(time(23), time(22, 30), time(7))
    assert is_quiet_time(time(6, 59), time(22, 30), time(7))
    assert not is_quiet_time(time(12), time(22, 30), time(7))
    assert quiet_period_end_utc(
        datetime(2026, 7, 14, 4, 0, tzinfo=UTC),
        "America/Chicago",
        time(22, 30),
        time(7),
    ) == datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


def test_same_local_reminder_time_produces_different_utc_runs():
    after = datetime(2026, 7, 13, 0, 0, tzinfo=UTC)
    central = next_scheduled_occurrence(
        after_utc=after,
        local_time=time(10),
        days_of_week=set(range(7)),
        timezone_name="America/Chicago",
    )
    mountain = next_scheduled_occurrence(
        after_utc=after,
        local_time=time(10),
        days_of_week=set(range(7)),
        timezone_name="America/Denver",
    )
    assert central == datetime(2026, 7, 13, 15, 0, tzinfo=UTC)
    assert mountain == datetime(2026, 7, 13, 16, 0, tzinfo=UTC)


def test_daily_task_generation_is_user_scoped_and_idempotent():
    with Session(engine) as first, Session(engine) as second:
        user = profile("America/Chicago")
        first.add(user)
        first.flush()
        seed_profile(first, user)
        first.commit()
        first.info["profile_id"] = user.id
        second.info["profile_id"] = user.id
        day = datetime(2026, 7, 13).date()
        initial = ensure_tasks(first, day)
        repeated = ensure_tasks(second, day)
        assert len(initial) == len(repeated)
        assert {task.id for task in initial} == {task.id for task in repeated}


def test_completion_keeps_original_local_date_and_timezone_after_change(client):
    task = client.get("/api/today").json()["tasks"][0]
    assert client.post(f"/api/tasks/{task['id']}/complete", json={}).status_code == 200
    with Session(engine) as db:
        before = db.scalar(
            select(models.TaskCompletion).where(
                models.TaskCompletion.daily_task_id == task["id"]
            )
        )
        original = (before.user_local_date, before.timezone_at_completion)
    response = client.put(
        "/api/settings",
        json={
            "display_name": "Timezone traveler",
            "starting_weight_kg": 99,
            "timezone": "America/Denver",
            "caffeine_cutoff": "14:00",
            "water_target_ml": 2000,
            "weight_milestones": [94, 90, 85],
        },
    )
    assert response.status_code == 200
    with Session(engine) as db:
        after = db.scalar(
            select(models.TaskCompletion).where(
                models.TaskCompletion.daily_task_id == task["id"]
            )
        )
        assert (after.user_local_date, after.timezone_at_completion) == original


class RecordingSender:
    def __init__(self):
        self.targets: list[str] = []

    def send(self, target: str, title: str, message: str):
        self.targets.append(target)
        return True, None


def test_durable_worker_deduplicates_and_uses_owning_users_target():
    due = datetime.now(UTC) - timedelta(minutes=1)
    with Session(engine) as db:
        user = profile("America/Chicago")
        db.add(user)
        db.flush()
        db.add(
            models.UserSetting(
                profile_id=user.id,
                key="notification_target",
                value="notify.mobile_app_private_phone",
            )
        )
        db.add(
            models.ReminderRule(
                profile_id=user.id,
                key="water",
                local_time=time(10),
                days_of_week="0,1,2,3,4,5,6",
                next_run_at_utc=due,
            )
        )
        db.commit()
        sender = RecordingSender()
        assert process_due_reminders(db, sender) == 1
    with Session(engine) as restarted_worker:
        assert process_due_reminders(restarted_worker, sender) == 0
        assert sender.targets == ["notify.mobile_app_private_phone"]
        assert (
            restarted_worker.scalar(
                select(func.count()).select_from(models.NotificationDelivery)
            )
            == 1
        )


def test_worker_defers_during_user_local_quiet_hours():
    now = datetime(2026, 7, 14, 4, 0, tzinfo=UTC)  # 11 PM in Chicago
    with Session(engine) as db:
        user = profile("America/Chicago")
        db.add(user)
        db.flush()
        db.add_all(
            [
                models.UserSetting(
                    profile_id=user.id, key="quiet_hours_start", value="22:30"
                ),
                models.UserSetting(
                    profile_id=user.id, key="quiet_hours_end", value="07:00"
                ),
                models.UserSetting(
                    profile_id=user.id,
                    key="notification_target",
                    value="notify.mobile_app_private_phone",
                ),
            ]
        )
        rule = models.ReminderRule(
            profile_id=user.id,
            key="water",
            local_time=time(23),
            days_of_week="0,1,2,3,4,5,6",
            next_run_at_utc=now - timedelta(minutes=1),
        )
        db.add(rule)
        db.commit()
        sender = RecordingSender()
        assert process_due_reminders(db, sender, now) == 0
        assert sender.targets == []
        db.refresh(rule)
        assert rule.next_run_at_utc.replace(tzinfo=UTC) == datetime(
            2026, 7, 14, 12, 0, tzinfo=UTC
        )


def test_timezone_change_recalculates_only_the_owning_users_schedule():
    now = datetime(2026, 7, 13, 0, 0, tzinfo=UTC)
    with Session(engine) as db:
        changed = profile("America/Chicago")
        unchanged = profile("America/Phoenix")
        db.add_all([changed, unchanged])
        db.flush()
        changed_rule = models.ReminderRule(
            profile_id=changed.id,
            key="water",
            local_time=time(10),
            days_of_week="0,1,2,3,4,5,6",
            next_run_at_utc=datetime(2026, 7, 13, 15, tzinfo=UTC),
        )
        unchanged_rule = models.ReminderRule(
            profile_id=unchanged.id,
            key="water",
            local_time=time(10),
            days_of_week="0,1,2,3,4,5,6",
            next_run_at_utc=datetime(2026, 7, 13, 17, tzinfo=UTC),
        )
        db.add_all([changed_rule, unchanged_rule])
        db.flush()
        changed.timezone = "America/Denver"
        recalculate_user_reminders(db, changed, now)
        assert changed_rule.next_run_at_utc == datetime(2026, 7, 13, 16, tzinfo=UTC)
        assert unchanged_rule.next_run_at_utc == datetime(2026, 7, 13, 17, tzinfo=UTC)

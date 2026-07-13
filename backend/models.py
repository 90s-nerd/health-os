from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def now() -> datetime:
    return datetime.now().astimezone()


class Profile(Base):
    __tablename__ = "app_profile"
    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(default="John")
    timezone: Mapped[str] = mapped_column(default="America/Chicago")
    height_cm: Mapped[float] = mapped_column(default=183)
    starting_weight_kg: Mapped[float] = mapped_column(default=99)
    pin_hash: Mapped[str | None]
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    must_change_pin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Habit(Base):
    __tablename__ = "habits"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("app_profile.id"), index=True)
    key: Mapped[str] = mapped_column(index=True)
    name: Mapped[str]
    description: Mapped[str] = mapped_column(default="")
    category: Mapped[str]
    icon: Mapped[str] = mapped_column(default="circle")
    suggested_time: Mapped[time | None] = mapped_column(Time)
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    minimum_label: Mapped[str | None]
    numeric_target: Mapped[float | None]
    sort_order: Mapped[int] = mapped_column(default=0)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    schedules: Mapped[list["HabitSchedule"]] = relationship(cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("profile_id", "key"),)


class HabitSchedule(Base):
    __tablename__ = "habit_schedules"
    id: Mapped[int] = mapped_column(primary_key=True)
    habit_id: Mapped[int] = mapped_column(ForeignKey("habits.id"), index=True)
    weekday: Mapped[int]
    required_override: Mapped[bool | None] = mapped_column(Boolean)
    relaxed_override: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("habit_id", "weekday"),)


class DailyTask(Base):
    __tablename__ = "daily_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    habit_id: Mapped[int] = mapped_column(ForeignKey("habits.id"), index=True)
    task_date: Mapped[date] = mapped_column(Date, index=True)
    required: Mapped[bool]
    habit: Mapped[Habit] = relationship()
    __table_args__ = (UniqueConstraint("habit_id", "task_date"),)


class TaskCompletion(Base):
    __tablename__ = "task_completions"
    id: Mapped[int] = mapped_column(primary_key=True)
    daily_task_id: Mapped[int] = mapped_column(ForeignKey("daily_tasks.id"), unique=True)
    state: Mapped[str] = mapped_column(default="completed")
    minimum_version: Mapped[bool] = mapped_column(Boolean, default=False)
    numeric_value: Mapped[float | None]
    notes: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ExerciseSession(Base):
    __tablename__ = "exercise_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("app_profile.id"), index=True)
    session_date: Mapped[date] = mapped_column(Date, index=True)
    activity: Mapped[str]
    planned_minutes: Mapped[int] = mapped_column(default=20)
    actual_minutes: Mapped[int] = mapped_column(default=0)
    effort: Mapped[int | None]
    minimum_version: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(default="completed")
    notes: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MealCheckin(Base):
    __tablename__ = "meal_checkins"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("app_profile.id"), index=True)
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    meal_type: Mapped[str]
    protein: Mapped[bool] = mapped_column(Boolean, default=False)
    vegetables: Mapped[bool] = mapped_column(Boolean, default=False)
    fruit: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    photo_path: Mapped[str | None]


class HydrationEntry(Base):
    __tablename__ = "hydration_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("app_profile.id"), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    amount_ml: Mapped[int] = mapped_column(default=350)


class CaffeineEntry(Base):
    __tablename__ = "caffeine_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("app_profile.id"), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    beverage: Mapped[str]
    servings: Mapped[float] = mapped_column(default=1)


class AlcoholEntry(Base):
    __tablename__ = "alcohol_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("app_profile.id"), index=True)
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    drink_type: Mapped[str]
    drinks: Mapped[float]
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)
    water_consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    plans_to_drive: Mapped[bool] = mapped_column(Boolean, default=False)


class SleepEntry(Base):
    __tablename__ = "sleep_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("app_profile.id"), index=True)
    sleep_date: Mapped[date] = mapped_column(Date, index=True)
    intended_bedtime: Mapped[time | None] = mapped_column(Time)
    actual_bedtime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    intended_wake_time: Mapped[time | None] = mapped_column(Time)
    actual_wake_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    minutes_asleep: Mapped[int]
    quality: Mapped[int]
    awakenings: Mapped[int | None]
    late_caffeine: Mapped[bool] = mapped_column(Boolean, default=False)
    late_meal: Mapped[bool] = mapped_column(Boolean, default=False)
    alcohol: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("profile_id", "sleep_date"),)


class WeightEntry(Base):
    __tablename__ = "weight_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("app_profile.id"), index=True)
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    weight_kg: Mapped[float]
    waist_cm: Mapped[float | None]
    notes: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("profile_id", "entry_date"),)


class Callout(Base):
    __tablename__ = "callouts"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(unique=True)
    type: Mapped[str]
    priority: Mapped[int]
    title: Mapped[str]
    message: Mapped[str]
    suggested_action: Mapped[str | None]
    reason: Mapped[str]
    dismissible: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_rule: Mapped[str]
    severity: Mapped[str]


class CalloutDismissal(Base):
    __tablename__ = "callout_dismissals"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("app_profile.id"), index=True)
    callout_id: Mapped[int] = mapped_column(ForeignKey("callouts.id"))
    dismissed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class UserSetting(Base):
    __tablename__ = "user_settings"
    profile_id: Mapped[int] = mapped_column(ForeignKey("app_profile.id"), primary_key=True)
    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class ReminderRule(Base):
    __tablename__ = "reminder_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("app_profile.id"), index=True)
    key: Mapped[str]
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    quiet_start: Mapped[time | None] = mapped_column(Time)
    quiet_end: Mapped[time | None] = mapped_column(Time)
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("profile_id", "key"),)


class ExternalEntityMapping(Base):
    __tablename__ = "external_entity_mappings"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("app_profile.id"), index=True)
    metric: Mapped[str]
    entity_id: Mapped[str]
    __table_args__ = (UniqueConstraint("profile_id", "metric"),)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("app_profile.id"), index=True)
    event_type: Mapped[str]
    entity_type: Mapped[str]
    entity_id: Mapped[str | None]
    details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

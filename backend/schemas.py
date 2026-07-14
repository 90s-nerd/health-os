from datetime import date, datetime, time
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator


class TaskAction(BaseModel):
    minimum_version: bool = False
    numeric_value: float | None = None
    notes: str | None = Field(default=None, max_length=1000)


PlanCategory = Literal["movement", "hydration", "nutrition", "sleep", "weight", "planning"]


class HabitCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    category: PlanCategory = "planning"
    suggested_time: time | None = None
    required: bool = True
    minimum_label: str | None = Field(default=None, max_length=120)
    paused: bool = False
    days: list[int] = Field(min_length=1, max_length=7)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name cannot be empty")
        return value

    @field_validator("description", "minimum_label")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("days")
    @classmethod
    def valid_days(cls, values: list[int]) -> list[int]:
        if any(value < 0 or value > 6 for value in values):
            raise ValueError("Weekdays must be between 0 and 6")
        return sorted(set(values))


class HabitUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    category: PlanCategory | None = None
    suggested_time: time | None = None
    required: bool | None = None
    minimum_label: str | None = Field(default=None, max_length=120)
    paused: bool | None = None
    days: list[int] | None = Field(default=None, min_length=1, max_length=7)

    @field_validator("name")
    @classmethod
    def clean_optional_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Name cannot be empty")
        return value

    @field_validator("description", "minimum_label")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("days")
    @classmethod
    def valid_optional_days(cls, values: list[int] | None) -> list[int] | None:
        if values is None:
            return None
        if any(value < 0 or value > 6 for value in values):
            raise ValueError("Weekdays must be between 0 and 6")
        return sorted(set(values))


class ExerciseIn(BaseModel):
    session_date: date
    activity: str
    planned_minutes: int = Field(20, ge=1, le=300)
    actual_minutes: int = Field(0, ge=0, le=600)
    effort: int | None = Field(None, ge=1, le=5)
    minimum_version: bool = False
    status: str = "completed"
    notes: str | None = None


class SleepIn(BaseModel):
    sleep_date: date
    intended_bedtime: time | None = None
    actual_bedtime: datetime | None = None
    intended_wake_time: time | None = None
    actual_wake_time: datetime | None = None
    minutes_asleep: int = Field(ge=0, le=1440)
    quality: int = Field(ge=1, le=5)
    awakenings: int | None = Field(None, ge=0, le=30)
    late_caffeine: bool = False
    late_meal: bool = False
    alcohol: bool = False
    notes: str | None = None


class WeightIn(BaseModel):
    entry_date: date
    weight_kg: float = Field(gt=20, lt=400)
    waist_cm: float | None = Field(None, gt=30, lt=300)
    notes: str | None = None


class HydrationIn(BaseModel):
    amount_ml: int = Field(350, ge=50, le=3000)


class CaffeineIn(BaseModel):
    beverage: str = "coffee"
    servings: float = Field(1, gt=0, le=10)


class AlcoholIn(BaseModel):
    entry_date: date
    drink_type: str
    drinks: float = Field(gt=0, le=30)
    start_time: time | None = None
    end_time: time | None = None
    water_consumed: bool = False
    plans_to_drive: bool = False


class MealIn(BaseModel):
    entry_date: date
    meal_type: str
    protein: bool = False
    vegetables: bool = False
    fruit: bool = False
    notes: str | None = None


class LoginIn(BaseModel):
    pin: str = Field(min_length=4, max_length=4, pattern=r"^\d{4}$")
    keep_signed_in: bool = False


class PinChangeIn(BaseModel):
    current_pin: str | None = Field(
        default=None, min_length=4, max_length=4, pattern=r"^\d{4}$"
    )
    new_pin: str = Field(min_length=4, max_length=4, pattern=r"^\d{4}$")


class HouseholdMemberIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    pin: str = Field(min_length=4, max_length=4, pattern=r"^\d{4}$")


class MemberSetupIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    timezone: str = Field(min_length=1, max_length=80)
    starting_weight_kg: float = Field(gt=20, lt=400)
    height_cm: float | None = Field(default=None, gt=80, lt=250)
    water_target_ml: int = Field(default=2000, ge=250, le=10000)
    new_pin: str = Field(min_length=4, max_length=4, pattern=r"^\d{4}$")

    @field_validator("timezone")
    @classmethod
    def member_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Use a valid IANA timezone such as America/Chicago") from exc
        return value


class OnboardingIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    pin: str = Field(min_length=4, max_length=4, pattern=r"^\d{4}$")
    timezone: str = Field(min_length=1, max_length=80)
    starting_weight_kg: float = Field(gt=20, lt=400)
    height_cm: float | None = Field(default=None, gt=80, lt=250)
    water_target_ml: int = Field(default=2000, ge=250, le=10000)

    @field_validator("timezone")
    @classmethod
    def onboarding_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Use a valid IANA timezone such as America/Chicago") from exc
        return value


class HomeAssistantOnboardingIn(BaseModel):
    timezone: str = Field(min_length=1, max_length=80)
    starting_weight_kg: float = Field(gt=20, lt=400)
    height_cm: float | None = Field(default=None, gt=80, lt=250)
    water_target_ml: int = Field(default=2000, ge=250, le=10000)

    @field_validator("timezone")
    @classmethod
    def onboarding_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Use a valid IANA timezone such as America/Chicago") from exc
        return value


class TravelTimezoneIn(BaseModel):
    timezone: str = Field(min_length=1, max_length=80)
    expires_at: datetime

    @field_validator("timezone")
    @classmethod
    def travel_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Use a valid IANA timezone such as America/Chicago") from exc
        return value


class AppSettingsIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    starting_weight_kg: float | None = Field(default=None, gt=20, lt=400)
    timezone: str = Field(min_length=1, max_length=80)
    caffeine_cutoff: time
    water_target_ml: int = Field(ge=250, le=10000)
    weight_milestones: list[float] = Field(min_length=1, max_length=10)
    notification_target: str = Field(default="", max_length=160)
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None
    timezone_mismatch_alerts: bool = True
    friday_reminders: Literal["normal", "gentle", "paused"] = "gentle"
    saturday_reminders: Literal["normal", "gentle", "paused"] = "gentle"
    reminders_paused: bool = False
    urgent_bypasses_quiet_hours: bool = False

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Use a valid IANA timezone such as America/Chicago") from exc
        return value

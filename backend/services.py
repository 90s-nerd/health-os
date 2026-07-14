import json
from datetime import date, datetime, timedelta
from statistics import mean

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_config
from .models import (
    AlcoholEntry,
    DailyTask,
    ExerciseSession,
    Habit,
    HabitSchedule,
    Profile,
    Setting,
    SleepEntry,
    TaskCompletion,
    UserSetting,
    WeightEntry,
)
from .time_service import UserClock

MODES = {
    0: ("Standard Day", "A steady start to the week."),
    1: ("Standard Day", "Keep the routine simple."),
    2: ("Standard Day", "Midweek consistency counts."),
    3: ("Standard Day", "A short version still protects the habit."),
    4: ("Relaxed Friday", "Flexible evening · Enjoy responsibly"),
    5: ("Relaxed Saturday", "Recovery counts · Minimum movement is enough"),
    6: ("Sunday Reset", "A gentle reset for the week ahead."),
}

DEFAULT_HABITS = [
    (
        "wake",
        "Wake in your target window",
        "Start without rushing.",
        "sleep",
        "sunrise",
        "07:00",
        True,
        None,
        [0, 1, 2, 3, 4, 6],
    ),
    (
        "water",
        "Morning water",
        "One large glass after waking.",
        "hydration",
        "droplets",
        "07:10",
        True,
        None,
        range(7),
    ),
    (
        "breakfast",
        "Protein-focused first meal",
        "Keep it easy and satisfying.",
        "nutrition",
        "egg",
        "08:00",
        True,
        None,
        range(7),
    ),
    (
        "work_water",
        "Water during the day",
        "A few steady refills are enough.",
        "hydration",
        "glass-water",
        "11:00",
        True,
        None,
        range(7),
    ),
    (
        "lunch",
        "Balanced lunch",
        "Include protein and something colorful.",
        "nutrition",
        "salad",
        "12:30",
        True,
        None,
        range(7),
    ),
    (
        "lunch_walk",
        "Walk after lunch",
        "Five to ten minutes when practical.",
        "movement",
        "footprints",
        "13:00",
        False,
        "5-minute walk",
        [0, 1, 2, 3, 4],
    ),
    (
        "movement",
        "Today’s movement",
        "Treadmill, bike, or an enjoyable walk.",
        "movement",
        "activity",
        "18:30",
        True,
        "10-minute minimum",
        [0, 2, 3, 6],
    ),
    (
        "friday_walk",
        "Optional recovery walk",
        "Ten gentle minutes counts fully.",
        "movement",
        "footprints",
        "18:00",
        False,
        "10-minute walk",
        [4],
    ),
    (
        "saturday_move",
        "Enjoyable movement",
        "Outside, treadmill, or bike—your choice.",
        "movement",
        "bike",
        "14:00",
        False,
        "10-minute stroll",
        [5],
    ),
    (
        "dinner",
        "Protein and vegetables",
        "A simple dinner is a good dinner.",
        "nutrition",
        "utensils",
        "19:30",
        True,
        None,
        range(7),
    ),
    (
        "wind_down",
        "Begin winding down",
        "Lower the lights and let the day soften.",
        "sleep",
        "moon",
        "21:30",
        True,
        "10 quiet minutes",
        [0, 1, 2, 3, 6],
    ),
    (
        "phone_away",
        "Put the phone away",
        "Give sleep a little room to arrive.",
        "sleep",
        "smartphone-off",
        "22:30",
        True,
        None,
        [0, 1, 2, 3, 6],
    ),
    (
        "bed",
        "Target sleep window",
        "Aim for around 11:00 PM.",
        "sleep",
        "bed",
        "23:00",
        True,
        None,
        [0, 1, 2, 3, 6],
    ),
    (
        "water_before_bed",
        "Water before bed",
        "A gentle hydration reminder for a social evening.",
        "hydration",
        "cup-soda",
        "23:30",
        False,
        None,
        [4, 5],
    ),
    (
        "weight",
        "Weekly weight",
        "One reading; the trend matters more.",
        "weight",
        "scale",
        "08:00",
        True,
        None,
        [6],
    ),
    (
        "weekly_review",
        "Review the past week",
        "Notice what worked without judging the rest.",
        "planning",
        "clipboard-check",
        "16:00",
        True,
        None,
        [6],
    ),
    (
        "meal_plan",
        "Choose easy meals",
        "Pick a few meals or groceries for the week.",
        "planning",
        "shopping-basket",
        "17:00",
        True,
        None,
        [6],
    ),
]


USER_DEFAULTS = {
    "caffeine_cutoff": "14:00",
    "weight_milestones": "94,90,88,85",
    "water_target_ml": "2000",
    "notification_target": "",
    "quiet_hours_start": "22:30",
    "quiet_hours_end": "07:00",
    "timezone_mismatch_alerts": "true",
    "friday_reminders": "gentle",
    "saturday_reminders": "gentle",
    "reminders_paused": "false",
    "urgent_bypasses_quiet_hours": "false",
}


def current_profile(db: Session) -> Profile:
    profile_id = db.info.get("profile_id")
    profile = db.get(Profile, profile_id) if profile_id else None
    if not profile:
        raise RuntimeError("No authenticated Health OS user is available")
    return profile


def user_setting(db: Session, key: str, default: str | None = None) -> str | None:
    profile = current_profile(db)
    item = db.get(UserSetting, (profile.id, key))
    return item.value if item else default


def seed_profile(db: Session, profile: Profile) -> None:
    if not db.scalar(select(Habit.id).where(Habit.profile_id == profile.id)):
        for order, row in enumerate(DEFAULT_HABITS):
            key, name, desc, category, icon, clock, required, minimum, days = row
            hour, minute = (int(x) for x in clock.split(":"))
            habit = Habit(
                profile_id=profile.id,
                key=key,
                name=name,
                description=desc,
                category=category,
                icon=icon,
                suggested_time=datetime.min.replace(hour=hour, minute=minute).time(),
                required=required,
                minimum_label=minimum,
                sort_order=order,
            )
            db.add(habit)
            db.flush()
            for day in days:
                optional_weekend = day in (4, 5) and category in ("movement", "sleep")
                db.add(
                    HabitSchedule(
                        habit_id=habit.id,
                        weekday=day,
                        required_override=False if optional_weekend else None,
                        relaxed_override=day in (4, 5),
                    )
                )
    for key, value in USER_DEFAULTS.items():
        if db.get(UserSetting, (profile.id, key)) is None:
            db.add(UserSetting(profile_id=profile.id, key=key, value=value))


def seed(db: Session) -> None:
    defaults = {
        "allow_embedding": "true" if get_config().frame_ancestors.strip() else "false",
        "embedding_origins": get_config().frame_ancestors.replace("'self'", "").strip(),
    }
    for key, value in defaults.items():
        if db.get(Setting, key) is None:
            db.add(Setting(key=key, value=value))
    db.commit()


def app_timezone(db: Session) -> str:
    return UserClock(current_profile(db)).timezone_name


def local_today(db: Session) -> date:
    return UserClock(current_profile(db)).local_date()


def mode_for(day: date) -> dict:
    name, subtitle = MODES[day.weekday()]
    return {"name": name, "subtitle": subtitle, "flexible": day.weekday() in (4, 5)}


def ensure_tasks(db: Session, day: date) -> list[DailyTask]:
    profile = current_profile(db)
    scheduled = db.scalars(
        select(HabitSchedule)
        .join(Habit)
        .where(HabitSchedule.weekday == day.weekday(), Habit.profile_id == profile.id)
    ).all()
    for schedule in scheduled:
        habit = db.get(Habit, schedule.habit_id)
        if habit and not habit.paused and not habit.archived_at:
            exists = db.scalar(
                select(DailyTask).where(DailyTask.habit_id == habit.id, DailyTask.task_date == day)
            )
            if not exists:
                db.add(
                    DailyTask(
                        habit_id=habit.id,
                        task_date=day,
                        required=schedule.required_override
                        if schedule.required_override is not None
                        else habit.required,
                    )
                )
    db.commit()
    return list(
        db.scalars(
            select(DailyTask)
            .join(Habit)
            .where(DailyTask.task_date == day, Habit.profile_id == profile.id)
            .order_by(Habit.suggested_time.is_(None), Habit.suggested_time, Habit.sort_order)
        )
    )


def task_dict(db: Session, task: DailyTask, now_local: datetime) -> dict:
    completion = db.scalar(select(TaskCompletion).where(TaskCompletion.daily_task_id == task.id))
    suggested = task.habit.suggested_time
    available = not suggested or now_local.time() >= suggested
    return {
        "id": task.id,
        "habit_id": task.habit_id,
        "key": task.habit.key,
        "name": task.habit.name,
        "description": task.habit.description,
        "category": task.habit.category,
        "icon": task.habit.icon,
        "suggested_time": suggested.strftime("%I:%M %p").lstrip("0") if suggested else None,
        "required": task.required,
        "minimum_label": task.habit.minimum_label,
        "state": completion.state if completion else ("available" if available else "upcoming"),
        "minimum_version": completion.minimum_version if completion else False,
        "numeric_value": completion.numeric_value if completion else None,
        "notes": completion.notes if completion else None,
    }


def completion_score(tasks: list[dict]) -> int:
    eligible = [x for x in tasks if x["required"] or x["state"] == "completed"]
    if not eligible:
        return 100
    completed = sum(x["state"] == "completed" for x in eligible)
    return round(100 * completed / len(eligible))


def next_action(
    tasks: list[dict], day: date, sleep_short: bool = False, now_local: datetime | None = None
) -> dict:
    if sleep_short:
        return {
            "title": "Keep today gentle",
            "message": "Your sleep was shorter than usual. Start with water and easy movement.",
            "task_id": next(
                (x["id"] for x in tasks if x["key"] == "water" and x["state"] != "completed"), None
            ),
        }
    if day.weekday() == 5:
        return {
            "title": "Hydrate after waking",
            "message": "Yesterday may have run late. Water and a gentle walk are enough today.",
            "task_id": next(
                (x["id"] for x in tasks if x["key"] == "water" and x["state"] != "completed"), None
            ),
        }
    if day.weekday() == 4 and now_local and now_local.hour >= 18:
        return {
            "title": "Enjoy your flexible evening",
            "message": "Have some water before bed, and choose a sober ride if you drink.",
            "task_id": next((x["id"] for x in tasks if x["key"] == "water_before_bed"), None),
        }
    pending = [x for x in tasks if x["state"] in ("available", "upcoming")]
    candidate = next(
        (x for x in pending if x["state"] == "available"), pending[0] if pending else None
    )
    if candidate:
        return {
            "title": candidate["name"],
            "message": candidate["description"],
            "task_id": candidate["id"],
        }
    return {
        "title": "You have done enough for today",
        "message": "Let the rest of the day be easy.",
        "task_id": None,
    }


def weight_series(db: Session, days: int | None = None) -> list[dict]:
    profile = current_profile(db)
    query = select(WeightEntry).where(WeightEntry.profile_id == profile.id).order_by(WeightEntry.entry_date)
    if days:
        query = query.where(WeightEntry.entry_date >= local_today(db) - timedelta(days=days))
    entries = list(db.scalars(query))
    result = []
    for idx, item in enumerate(entries):
        window = entries[max(0, idx - 6) : idx + 1]
        result.append(
            {
                "id": item.id,
                "date": item.entry_date.isoformat(),
                "weight": item.weight_kg,
                "average": round(mean(x.weight_kg for x in window), 2),
                "waist_cm": item.waist_cm,
                "notes": item.notes,
            }
        )
    return result


def generated_callouts(db: Session, day: date) -> list[dict]:
    profile = current_profile(db)
    items = []
    alcohol_drive = db.scalar(
        select(AlcoholEntry).where(
            AlcoholEntry.profile_id == profile.id,
            AlcoholEntry.entry_date == day,
            AlcoholEntry.plans_to_drive,
        )
    )
    if alcohol_drive:
        items.append(
            {
                "id": "alcohol-drive",
                "severity": "safety",
                "priority": 100,
                "title": "Please choose a sober ride",
                "message": "Alcohol and driving do not mix. Use a designated driver, rideshare, or stay where you are.",
                "suggested_action": "Make a sober transportation plan",
                "reason": "Alcohol was logged with possible driving",
                "dismissible": False,
            }
        )
    sleeps = list(
        db.scalars(
            select(SleepEntry)
            .where(SleepEntry.profile_id == profile.id)
            .order_by(SleepEntry.sleep_date.desc())
            .limit(2)
        )
    )
    if len(sleeps) == 2 and all(x.minutes_asleep < 360 for x in sleeps):
        items.append(
            {
                "id": "short-sleep",
                "severity": "attention",
                "priority": 80,
                "title": "Two short nights",
                "message": "Keep exercise gentle today and allow extra time to rest. This is not a diagnosis.",
                "suggested_action": "Choose the minimum movement version",
                "reason": "Two sleep check-ins under six hours",
                "dismissible": True,
            }
        )
    last_weight = db.scalar(
        select(func.max(WeightEntry.entry_date)).where(WeightEntry.profile_id == profile.id)
    )
    if not last_weight or (day - last_weight).days > 14:
        items.append(
            {
                "id": "weight-due",
                "severity": "informational",
                "priority": 35,
                "title": "A trend check would help",
                "message": "It has been a while since your last weight entry. One reading is enough.",
                "suggested_action": "Record weight when convenient",
                "reason": "No weight entry in more than 14 days",
                "dismissible": True,
            }
        )
    week_start = day - timedelta(days=day.weekday())
    movement = (
        db.scalar(
            select(func.count())
            .select_from(ExerciseSession)
            .where(
                ExerciseSession.session_date >= week_start, ExerciseSession.status == "completed"
                , ExerciseSession.profile_id == profile.id
            )
        )
        or 0
    )
    if movement >= 3:
        items.append(
            {
                "id": "movement-three",
                "severity": "encouragement",
                "priority": 30,
                "title": "Movement is becoming a pattern",
                "message": "You completed three movement sessions this week. Sustainable beats perfect.",
                "suggested_action": None,
                "reason": "Three completed sessions this week",
                "dismissible": True,
            }
        )
    return sorted(items, key=lambda x: x["priority"], reverse=True)[:3]


def audit(db: Session, event: str, entity: str, entity_id: int | None, details: dict | None = None):
    from .models import AuditEvent

    db.add(
        AuditEvent(
            profile_id=current_profile(db).id,
            event_type=event,
            entity_type=entity,
            entity_id=str(entity_id) if entity_id else None,
            details=json.dumps(details) if details else None,
        )
    )
